"""单图下载任务。

封装"一次下载尝试"的所有副作用（写 .part → 校验 → 原子替换 → 延迟），
将网络/磁盘细节从 Worker 编排层抽离。
"""
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from utils.config import Config
from utils.logger import logger
from core.download.image_integrity import (
    atomic_replace,
    looks_like_image,
    safe_unlink,
)
from core.download.http_client import HttpClient


class DownloadTask:
    """单图下载任务：可被线程池反复调用执行重试/代理重试。

    通过构造函数注入 :class:`HttpClient`，避免在任务内部直接请求外部资源，
    便于测试时替换为 Mock。
    """

    def __init__(self, img_id: int, http_client: HttpClient,
                 is_cancelled: Callable[[], bool],
                 status_emitter: Optional[Callable[[str], None]] = None):
        self.img_id = img_id
        self.http_client = http_client
        self._is_cancelled = is_cancelled
        self._status = status_emitter or (lambda _msg: None)
        self._cancelled = False
        self._stop_proxy_retry = False

    @property
    def was_cancelled(self) -> bool:
        """Return whether this task stopped because the worker was cancelled."""
        return self._cancelled

    def _check_cancelled(self) -> bool:
        """Record cancellation once and return the current state."""
        if self._is_cancelled():
            self._cancelled = True
            return True
        return False

    def _interruptible_sleep(self, seconds: float,
                             should_stop: Callable[[], bool]) -> bool:
        """Sleep in short slices; return False if should_stop() fired first."""
        deadline = time.monotonic() + max(0.0, seconds)
        while True:
            if should_stop():
                return False
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return True
            time.sleep(min(0.25, remaining))

    def _sleep_with_cancel(self, seconds: float) -> bool:
        """Sleep in short slices so cancellation is observed promptly."""
        return self._interruptible_sleep(seconds, self._check_cancelled)

    def _rate_limit_delay(self, seconds: float) -> None:
        """Post-success politeness delay: cut short on cancellation without
        marking the (already successful) task as cancelled."""
        self._interruptible_sleep(seconds, self._is_cancelled)

    def run_with_proxy_retry(self) -> bool:
        """Run ordinary retries, then proxy retries for retryable failures."""
        for proxy_retry in range(Config.PROXY_RETRY_TIMES):
            if self._check_cancelled():
                return False
            if self._attempt_once():
                logger.info(f"Successfully downloaded image {self.img_id}")
                return True
            if self._cancelled or self._stop_proxy_retry:
                break
            if proxy_retry < Config.PROXY_RETRY_TIMES - 1:
                self._status(
                    f"[{self.img_id}] proxy retry "
                    f"{proxy_retry + 1}/{Config.PROXY_RETRY_TIMES}..."
                )
                if not self._sleep_with_cancel(Config.PROXY_RETRY_DELAY):
                    return False

        logger.warning(f"Failed to download image {self.img_id}")
        return False

    # ------------------------------------------------------------------
    # 内部：单次下载 + 完整性校验
    # ------------------------------------------------------------------
    def _attempt_once(self) -> bool:
        """单次下载尝试：先写 .part，校验通过后原子替换到 .jpg。"""
        if self._check_cancelled():
            return False

        save_path = Config.COMIC_DIR / f"{self.img_id}.jpg"
        tmp_path = Config.COMIC_DIR / f"{self.img_id}.jpg.part"
        min_size = getattr(Config, "MIN_VALID_DOWNLOAD_BYTES", 1024)

        for retry in range(Config.RETRY_TIMES):
            if self._check_cancelled():
                return False

            # 每次重试前先清掉旧 .part 残留
            safe_unlink(tmp_path)

            response = None
            try:
                img_url = Config.BASE_URL.format(self.img_id)
                response = self.http_client.download_stream(img_url)
                response.raise_for_status()

                with open(tmp_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=1024):
                        if self._check_cancelled():
                            return False
                        if chunk:
                            f.write(chunk)

                # HTTP 200 may still return an empty response, an HTML/JSON
                # error page, or a body cut short by the connection dropping.
                if not looks_like_image(tmp_path, min_size):
                    content_type = ""
                    declared_length = None
                    if response is not None:
                        content_type = str(
                            response.headers.get("Content-Type", "")
                        ).lower()
                        declared_length = response.headers.get("Content-Length")
                    try:
                        actual_size = (
                            tmp_path.stat().st_size if tmp_path.exists() else 0
                        )
                    except OSError:
                        actual_size = 0

                    # 只有"完整收到的确定性坏响应"（HTML/JSON 错误页、与声明
                    # 长度一致的非图片体）才放弃代理重试；未收满声明长度属于
                    # 瞬时网络截断，代理重试仍有机会恢复。
                    truncated = False
                    if declared_length is not None:
                        try:
                            truncated = actual_size < int(declared_length)
                        except (TypeError, ValueError):
                            pass
                    deterministic_bad_body = not truncated and (
                        declared_length is not None
                        or any(
                            marker in content_type
                            for marker in ("text/", "html", "json")
                        )
                    )
                    if deterministic_bad_body:
                        self._stop_proxy_retry = True
                    logger.warning(
                        f"Downloaded file failed integrity check for {self.img_id}; "
                        f"content_type={content_type or 'unknown'}, "
                        f"size={actual_size}, "
                        f"declared_length={declared_length or 'unknown'}, "
                        f"treating as failure"
                    )
                    safe_unlink(tmp_path)
                    if not self._check_cancelled() and retry < Config.RETRY_TIMES - 1:
                        if not self._sleep_with_cancel(Config.RETRY_DELAY):
                            return False
                        continue
                    return False

                if save_path.exists():
                    safe_unlink(save_path)

                # 原子替换
                if not atomic_replace(tmp_path, save_path):
                    return False
                # The file is fully persisted; the politeness delay below must
                # not flip this task into the cancelled bucket.
                self._rate_limit_delay(Config.REQUEST_DELAY)
                return True

            except requests_exceptions.HTTPError as e:
                status_code = e.response.status_code if e.response is not None else 0
                logger.error(
                    f"[task_id={self.img_id}] HTTP {status_code} error: {e}"
                )
                safe_unlink(tmp_path)
                if status_code in [502, 503, 504]:
                    if not self._check_cancelled() and retry < Config.RETRY_TIMES - 1:
                        if not self._sleep_with_cancel(Config.RETRY_DELAY):
                            return False
                        continue
                break
            except requests_exceptions.RequestException as e:
                logger.error(
                    f"[task_id={self.img_id}] request error: {e}"
                )
                safe_unlink(tmp_path)
                if not self._check_cancelled() and retry < Config.RETRY_TIMES - 1:
                    if not self._sleep_with_cancel(Config.RETRY_DELAY):
                        return False
                    continue
                break
            except Exception as e:
                logger.error(
                    f"[task_id={self.img_id}] unknown error: {e}",
                    exc_info=True,
                )
                safe_unlink(tmp_path)
                break
            finally:
                # 确保 response 关闭连接
                try:
                    if response is not None:
                        response.close()
                except Exception:
                    pass

        # 全部重试失败 / 异常出口：保证不留下 .part / 半截文件
        safe_unlink(tmp_path)
        return False

    @staticmethod
    def make_record(img_id: int, success: bool, file_size: int = 0) -> dict:
        """构造下载记录的辅助方法，统一时间戳格式。"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if success:
            return {
                "status": "success",
                "downloaded_time": now,
                "file_size": file_size,
            }
        return {
            "status": "failed",
            "failed_time": now,
        }


# 延迟导入放在模块底部，避免在 import 阶段产生循环引用
from requests import exceptions as requests_exceptions  # noqa: E402
