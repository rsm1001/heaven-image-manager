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
from core.image_integrity import (
    atomic_replace,
    looks_like_image,
    safe_unlink,
)
from core.http_client import HttpClient


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

    def run_with_proxy_retry(self) -> bool:
        """按代理重试次数循环执行单次下载；任一次成功即返回 True。"""
        for proxy_retry in range(Config.PROXY_RETRY_TIMES):
            if self._is_cancelled():
                return False
            if self._attempt_once():
                logger.info(f"Successfully downloaded image {self.img_id}")
                return True
            if not self._is_cancelled() and proxy_retry < Config.PROXY_RETRY_TIMES - 1:
                self._status(
                    f"[{self.img_id}] 代理重试 {proxy_retry + 1}/{Config.PROXY_RETRY_TIMES}..."
                )
                time.sleep(Config.PROXY_RETRY_DELAY)

        logger.warning(f"Failed to download image {self.img_id}")
        return False

    # ------------------------------------------------------------------
    # 内部：单次下载 + 完整性校验
    # ------------------------------------------------------------------
    def _attempt_once(self) -> bool:
        """单次下载尝试：先写 .part，校验通过后原子替换到 .jpg。"""
        if self._is_cancelled():
            return False

        save_path = Config.COMIC_DIR / f"{self.img_id}.jpg"
        tmp_path = Config.COMIC_DIR / f"{self.img_id}.jpg.part"
        min_size = getattr(Config, "MIN_VALID_DOWNLOAD_BYTES", 1024)

        for retry in range(Config.RETRY_TIMES):
            if self._is_cancelled():
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
                        if self._is_cancelled():
                            return False
                        if chunk:
                            f.write(chunk)

                # 完整性校验：大小 + 头部魔数
                if not looks_like_image(tmp_path, min_size):
                    logger.warning(
                        f"Downloaded file failed integrity check for {self.img_id}; "
                        f"treating as failure"
                    )
                    safe_unlink(tmp_path)
                    if not self._is_cancelled() and retry < Config.RETRY_TIMES - 1:
                        time.sleep(Config.RETRY_DELAY)
                        continue
                    return False

                # 落盘前先确保没有同名目标
                if save_path.exists():
                    safe_unlink(save_path)

                # 原子替换
                if not atomic_replace(tmp_path, save_path):
                    return False
                time.sleep(Config.REQUEST_DELAY)
                return True

            except requests_exceptions.HTTPError as e:
                status_code = e.response.status_code if e.response is not None else 0
                logger.error(
                    f"[task_id={self.img_id}] HTTP {status_code} error: {e}"
                )
                safe_unlink(tmp_path)
                if status_code in [502, 503, 504]:
                    if not self._is_cancelled() and retry < Config.RETRY_TIMES - 1:
                        time.sleep(Config.RETRY_DELAY)
                        continue
                break
            except requests_exceptions.RequestException as e:
                logger.error(
                    f"[task_id={self.img_id}] request error: {e}"
                )
                safe_unlink(tmp_path)
                if not self._is_cancelled() and retry < Config.RETRY_TIMES - 1:
                    time.sleep(Config.RETRY_DELAY)
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
