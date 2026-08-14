"""下载器外观（Facade）。

本模块是对外公开的统一入口：

* :class:`ThumbnailDownloader` —— UI 层使用的简单门面。
* 下载模块入口：从本模块可直接 ``from core.download.downloader import DownloadWorker``
  / ``DownloadRecord`` / ``get_download_pool`` / ``shutdown_download_pool``。

具体职责已被拆分到下列子模块，遵循"垂直划分、依赖注入"原则：

* :mod:`core.download.download_pool`  —— 进程级线程池单例与工厂。
* :mod:`core.download.http_client`    —— HTTP 客户端适配器（requests 封装）。
* :mod:`core.download.image_integrity`—— 魔数校验、临时文件清理、原子替换。
* :mod:`core.download.download_record`—— 下载记录仓储（Repository）。
* :mod:`core.download.download_task`  —— 单图下载任务（含重试逻辑）。
* :mod:`core.download.download_worker`—— QThread 编排（信号 + 进度汇总）。
"""
from typing import Callable, Optional

from utils.logger import logger

# 下载模块的统一导出入口
from core.download.download_pool import (  # noqa: F401
    DEFAULT_MAX_WORKERS,
    get_download_pool,
    shutdown_download_pool,
)
from core.download.download_record import DownloadRecordRepository  # noqa: F401

# DownloadRecord 是历史类名，保留为 Repository 的别名以不破坏既有测试
DownloadRecord = DownloadRecordRepository
from core.download.download_worker import DownloadWorker  # noqa: F401


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
        """取消当前下载任务（如有）。

        不做 is_running 判断：worker.start() 之后、run() 真正执行之前存在
        窗口期，此时取消也必须生效（置标志对未启动的 worker 无副作用）。
        """
        if self.worker:
            self.worker.cancel_download()
            logger.info("Cancelled download")

    def shutdown(self, timeout_ms: int = 15000) -> None:
        """应用退出前调用：取消并等待 worker 线程结束。

        没有这次 join，Qt 会在线程仍运行时销毁 QThread（"QThread:
        Destroyed while thread is still running"），可能打断
        download_records.json / config.json 的写入。取消后任务最坏在
        HTTP 读超时（20s）内返回，这里给 15s 上限并在超时后记录警告。
        """
        if self.worker is None:
            return
        self.worker.cancel_download()
        if not self.worker.wait(timeout_ms):
            logger.warning(
                f"Download worker did not finish within {timeout_ms}ms "
                f"during shutdown"
            )
