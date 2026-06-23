"""下载编排 Worker（QThread）。

负责：
1. 扫描已存在/已完成的 ID，决定本次真正要下载的目标；
2. 将每个目标包装为 :class:`DownloadTask`，通过全局线程池并行执行；
3. 汇总进度并通过 Qt 信号回推 UI。

具体的"如何下载一张图"完全委托给 ``DownloadTask`` 与 ``HttpClient``，
本模块不直接 import requests / 拼装代理。
"""
import threading
import uuid
from concurrent.futures import as_completed
from datetime import datetime
from typing import Dict, List

from PyQt5.QtCore import QThread, pyqtSignal

from core.download_pool import get_download_pool
from core.download_record import DownloadRecordRepository
from core.download_task import DownloadTask
from core.http_client import create_http_client
from core.image_integrity import cleanup_stale_tmp_files, safe_unlink
from utils.config import Config
from utils.logger import logger

# 默认线程数（与下载池保持一致）
from core.download_pool import DEFAULT_MAX_WORKERS


class DownloadWorker(QThread):
    """下载工作线程（使用线程池并行下载）。"""

    # 进度信号：(当前完成数, 状态文本)
    progress_signal = pyqtSignal(int, str)
    # 完成信号：结果字典
    completed_signal = pyqtSignal(dict)
    # 状态信号：任意附加提示文本
    status_signal = pyqtSignal(str)

    def __init__(self, start_id: int, count: int,
                 max_workers: int = DEFAULT_MAX_WORKERS):
        super().__init__()
        self.request_id = uuid.uuid4().hex[:12]  # 请求追踪 ID，便于日志串联
        self.start_id = start_id
        self.count = count
        self.max_workers = max_workers
        self.is_running = False
        self.cancelled = False
        self._active_futures: List = []
        self._lock = threading.Lock()
        self._completed_count = 0
        self._success_count = 0
        self._fail_count = 0
        self._fail_ids: List[int] = []
        self._success_ids: List[int] = []
        self._skipped_ids: List[int] = []
        self._download_records: Dict[int, dict] = {}
        # 启动时清一次 .part 残留，并把清理数量带回 UI
        self._partial_files_cleaned = cleanup_stale_tmp_files(Config.COMIC_DIR, 0)

    # ------------------------------------------------------------------
    # 主流程
    # ------------------------------------------------------------------
    def run(self):
        """执行下载任务（线程池并行模式）。"""
        self.is_running = True
        self._completed_count = 0
        self._success_count = 0
        self._fail_count = 0
        self._fail_ids = []
        self._success_ids = []
        self._skipped_ids = []
        self._active_futures = []
        self._download_records = DownloadRecordRepository.load_all()

        if self._partial_files_cleaned:
            self.status_signal.emit(
                f"启动时已清理 {self._partial_files_cleaned} 个上次未完成的临时文件"
            )

        # 扫描已存在的文件和已成功下载的记录
        existing_file_ids = DownloadRecordRepository.existing_file_ids()
        completed_ids = DownloadRecordRepository.completed_ids()
        skip_ids = existing_file_ids | completed_ids

        # 计算本次实际需要下载的 ID 列表
        target_ids: List[int] = []
        for i in range(self.count):
            img_id = self.start_id + i
            if img_id in skip_ids:
                self._skipped_ids.append(img_id)
            else:
                target_ids.append(img_id)

        self.status_signal.emit(
            f"开始下载：从{self.start_id}开始，共{self.count}张"
            f"（并行{self.max_workers}线程，已跳过{len(self._skipped_ids)}张）"
        )
        logger.info(
            f"[request_id={self.request_id}] starting parallel download: "
            f"start={self.start_id}, count={self.count}, "
            f"max_workers={self.max_workers}, skip={len(self._skipped_ids)}"
        )

        if not target_ids:
            self.completed_signal.emit({
                "success": True,
                "success_count": 0,
                "fail_count": 0,
                "fail_ids": [],
                "total": self.count,
                "cancelled": False,
                "skipped": self._skipped_ids,
                "partial_files_cleaned": self._partial_files_cleaned,
            })
            self.is_running = False
            return

        pool = get_download_pool(self.max_workers)
        # 工厂方法：创建 HTTP 客户端（注入到每个 task）
        http_client = create_http_client()

        # 1. 提交所有下载任务到线程池
        for img_id in target_ids:
            if self.cancelled:
                break
            task = DownloadTask(
                img_id=img_id,
                http_client=http_client,
                is_cancelled=lambda: self.cancelled,
                status_emitter=lambda msg, _tid=img_id: self.status_signal.emit(msg),
            )
            future = pool.submit(task.run_with_proxy_retry)
            self._active_futures.append(future)

        # 2. 等待所有任务完成（使用 as_completed 实现实时反馈）
        futures_snapshot = list(self._active_futures)

        for future in as_completed(futures_snapshot):
            if self.cancelled:
                for f in futures_snapshot:
                    if not f.done():
                        f.cancel()
                break

            try:
                success = bool(future.result())
                # 通过 future 找回对应 img_id：保持提交顺序一一对应
                img_id = target_ids[futures_snapshot.index(future)]

                with self._lock:
                    self._completed_count += 1
                    if success:
                        self._success_count += 1
                        self._success_ids.append(img_id)
                        # 真实文件大小（落盘后才有意义）
                        final_path = Config.COMIC_DIR / f"{img_id}.jpg"
                        file_size = (
                            final_path.stat().st_size
                            if final_path.exists() else 0
                        )
                        self._download_records[img_id] = DownloadTask.make_record(
                            img_id, success=True, file_size=file_size
                        )
                    else:
                        self._fail_count += 1
                        self._fail_ids.append(img_id)
                        self._download_records[img_id] = DownloadTask.make_record(
                            img_id, success=False
                        )
                    current = self._completed_count

                self.progress_signal.emit(
                    current, f"{'成功' if success else '失败'} {img_id}"
                )

            except Exception as e:
                logger.error(
                    f"[request_id={self.request_id}] download task exception: {e}",
                    exc_info=True,
                )

        # 3. 保存下载记录
        DownloadRecordRepository.save_all(self._download_records)

        # 4. 发射完成信号
        final_result = {
            "success": not self.cancelled,
            "success_count": self._success_count,
            "fail_count": self._fail_count,
            "fail_ids": self._fail_ids,
            "success_ids": self._success_ids,
            "total": self.count,
            "cancelled": self.cancelled,
            "skipped": self._skipped_ids,
            "partial_files_cleaned": self._partial_files_cleaned,
        }

        self.completed_signal.emit(final_result)
        self.is_running = False
        logger.info(
            f"[request_id={self.request_id}] download completed: "
            f"success={self._success_count}, fail={self._fail_count}, "
            f"skipped={len(self._skipped_ids)}"
        )

    # ------------------------------------------------------------------
    # 控制接口
    # ------------------------------------------------------------------
    def cancel_download(self):
        """取消下载并清理 .part 残留。"""
        self.cancelled = True
        try:
            with self._lock:
                for f in self._active_futures:
                    f.cancel()
        except Exception:
            pass
        try:
            self.wait(3000)
        except Exception:
            pass
        # 兜底：取消时清掉 .part 残留
        try:
            for p in Config.COMIC_DIR.glob("*.jpg.part"):
                safe_unlink(p)
        except OSError:
            pass
