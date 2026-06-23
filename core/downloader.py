"""下载器外观（Facade）。

本模块是对外公开的统一入口：

* :class:`ThumbnailDownloader` —— UI 层使用的简单门面。
* 兼容旧导入路径：从本模块可直接 ``from core.downloader import DownloadWorker``
  / ``DownloadRecord`` / ``get_download_pool`` / ``shutdown_download_pool``。

具体职责已被拆分到下列子模块，遵循"垂直划分、依赖注入"原则：

* :mod:`core.download_pool`  —— 进程级线程池单例与工厂。
* :mod:`core.http_client`    —— HTTP 客户端适配器（requests 封装）。
* :mod:`core.image_integrity`—— 魔数校验、临时文件清理、原子替换。
* :mod:`core.download_record`—— 下载记录仓储（Repository）。
* :mod:`core.download_task`  —— 单图下载任务（含重试逻辑）。
* :mod:`core.download_worker`—— QThread 编排（信号 + 进度汇总）。
"""
from typing import Callable, Optional

from utils.logger import logger

# 兼容旧调用方：原 ``from core.downloader import ...`` 仍可用
from core.download_pool import (  # noqa: F401
    DEFAULT_MAX_WORKERS,
    get_download_pool,
    shutdown_download_pool,
)
from core.download_record import DownloadRecordRepository  # noqa: F401

# DownloadRecord 是历史类名，保留为 Repository 的别名以不破坏既有测试
DownloadRecord = DownloadRecordRepository
from core.download_worker import DownloadWorker  # noqa: F401


class ThumbnailDownloader:
    """缩略图下载器外观（UI 友好）。"""

    def __init__(self):
        self.worker: Optional[DownloadWorker] = None

    def start_download(self, start_id: int, count: int,
                       progress_callback: Callable = None,
                       completed_callback: Callable = None,
                       status_callback: Callable = None,
                       max_workers: int = DEFAULT_MAX_WORKERS) -> bool:
        """开始下载任务；返回 True 表示已成功提交，False 表示已有任务在跑。"""
        if self.worker and self.worker.isRunning():
            logger.warning("Download already in progress")
            return False

        self.worker = DownloadWorker(start_id, count, max_workers)

        if progress_callback:
            self.worker.progress_signal.connect(progress_callback)
        if completed_callback:
            self.worker.completed_signal.connect(completed_callback)
        if status_callback:
            self.worker.status_signal.connect(status_callback)

        self.worker.start()
        logger.info(
            f"Started download worker: start_id={start_id}, count={count}, "
            f"max_workers={max_workers}"
        )
        return True

    def cancel_download(self):
        """取消当前下载任务（如有）。"""
        if self.worker and self.worker.is_running:
            self.worker.cancel_download()
            logger.info("Cancelled download")
