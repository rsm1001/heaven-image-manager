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
from concurrent.futures import FIRST_COMPLETED, wait as futures_wait
from typing import Dict, List, Optional, Set

from PyQt5.QtCore import QThread, pyqtSignal

from core.download.download_pool import get_download_pool
from core.download.download_record import DownloadRecordRepository
from core.download.download_task import DownloadTask
from core.download.http_client import create_http_client
from core.download.image_integrity import cleanup_stale_tmp_files, safe_unlink
from utils.config import Config
from utils.logger import logger

# 默认线程数（与下载池保持一致）
from core.download.download_pool import DEFAULT_MAX_WORKERS


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
        self._cancelled_ids: List[int] = []
        self._download_records: Dict[int, dict] = {}
        # 启动时清一次 .part 残留，并把清理数量带回 UI
        self._partial_files_cleaned = cleanup_stale_tmp_files(Config.COMIC_DIR, 0)

    # ------------------------------------------------------------------
    # 主流程
    # ------------------------------------------------------------------
    def run(self):
        """执行下载任务（线程池并行模式）。

        completed_signal 由 finally 兜底：无论内部抛出什么异常，UI 都能收到
        完成回调并恢复按钮，不会被永久锁死。
        """
        self.is_running = True
        final_result = None
        try:
            final_result = self._run_impl()
        except Exception:
            logger.error(
                f"[request_id={self.request_id}] download worker crashed",
                exc_info=True,
            )
        finally:
            self.is_running = False
            if final_result is None:
                # 构造最小可用的兜底结果；再失败就发一个纯标记字典。
                try:
                    # 崩溃路径只汇总统计：不推进全局检查点（本次运行没有走到
                    # 正常的持久化流程），也不向 UI 报告检查点已保存。
                    final_result = self._build_final_result(
                        set(), records_saved=False, persist_checkpoint=False
                    )
                    final_result["success"] = False
                except Exception:
                    logger.error(
                        f"[request_id={self.request_id}] failed to build "
                        f"fallback result",
                        exc_info=True,
                    )
                    final_result = {
                        "success": False,
                        "success_count": self._success_count,
                        "fail_count": self._fail_count,
                        "fail_ids": self._fail_ids,
                        "cancelled_ids": self._cancelled_ids,
                        "success_ids": self._success_ids,
                        "total": self.count,
                        "cancelled": self.cancelled,
                        "skipped": self._skipped_ids,
                        "partial_files_cleaned": self._partial_files_cleaned,
                        "records_saved": False,
                        "last_contiguous_id": None,
                        "resume_id": self.start_id,
                        "checkpoint_saved": False,
                        "checkpoint_advanced": False,
                        "last_downloaded_id": None,
                        "next_start_id": None,
                        "global_next_start_id": None,
                    }
            self.completed_signal.emit(final_result)

    def _run_impl(self) -> dict:
        """run() 的主体逻辑，返回最终结果字典。"""
        self._completed_count = 0
        self._success_count = 0
        self._fail_count = 0
        self._fail_ids = []
        self._success_ids = []
        self._skipped_ids = []
        self._cancelled_ids = []
        self._active_futures = []
        self._download_records = DownloadRecordRepository.load_all()

        if self._partial_files_cleaned:
            self.status_signal.emit(
                f"启动时已清理 {self._partial_files_cleaned} 个上次未完成的临时文件"
            )

        # 扫描已存在的文件（含被整理进子目录的，见 existing_file_ids）。
        # Ignore stale success records; only current files are verified complete.
        existing_file_ids = DownloadRecordRepository.existing_file_ids()
        completed_ids = set(existing_file_ids)
        skip_ids = existing_file_ids

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
            final_result = self._build_final_result(completed_ids)
            logger.info(
                f"[request_id={self.request_id}] download skipped: "
                f"skip={len(self._skipped_ids)}, "
                f"next_start={final_result['next_start_id']}"
            )
            return final_result

        pool = get_download_pool(self.max_workers)
        # 工厂方法：创建 HTTP 客户端（注入到每个 task）
        http_client = create_http_client()

        # 1. 提交所有下载任务到线程池
        future_to_id = {}
        future_to_task = {}
        for idx, img_id in enumerate(target_ids):
            if self.cancelled:
                # 从未提交的目标也要进 cancelled 桶，保证各桶之和等于 total；
                # 一次性记账并只发一个进度信号。
                self._record_cancelled_batch(target_ids[idx:])
                break
            task = DownloadTask(
                img_id=img_id,
                http_client=http_client,
                is_cancelled=lambda: self.cancelled,
                status_emitter=lambda msg, _tid=img_id: self.status_signal.emit(msg),
            )
            future = pool.submit(task.run_with_proxy_retry)
            self._active_futures.append(future)
            future_to_id[future] = img_id
            future_to_task[future] = task

        # 2. 等待任务完成。取消时：未启动的 future 直接撤销并批量记账；
        #    已在运行的必须等它结束并按真实结果记账——中途遗弃会留下
        #    "文件已落盘却被报告为已取消、无记录"的孤儿，且重开下载时
        #    新任务会与仍握着 .part 的旧任务竞争同一文件。任务的
        #    is_cancelled 回调让其快速自行终止，最坏等到读超时（20s）。
        pending = set(self._active_futures)
        cancellation_dispatched = False
        while pending:
            if self.cancelled and not cancellation_dispatched:
                revoked = [f for f in pending if f.cancel()]
                pending.difference_update(revoked)
                self._record_cancelled_batch(
                    [future_to_id[f] for f in revoked]
                )
                cancellation_dispatched = True
                if not pending:
                    break

            done, pending = futures_wait(
                pending, timeout=0.2, return_when=FIRST_COMPLETED
            )
            for future in done:
                self._handle_finished_future(
                    future, future_to_id[future], future_to_task[future]
                )

        # 此刻所有任务都已结束：取消时在 worker 线程里清理 .part 残留，
        # 不会与仍在写盘的任务竞争删除。
        if self.cancelled:
            try:
                for p in Config.COMIC_DIR.glob("*.jpg.part"):
                    safe_unlink(p)
            except OSError:
                pass

        # Persist records, then calculate the safe continuation checkpoint.
        records_saved = DownloadRecordRepository.save_all(self._download_records)
        final_result = self._build_final_result(completed_ids, records_saved)

        logger.info(
            f"[request_id={self.request_id}] download completed: "
            f"success={self._success_count}, fail={self._fail_count}, "
            f"skipped={len(self._skipped_ids)}, "
            f"cancelled={self.cancelled}, "
            f"last_contiguous={final_result['last_contiguous_id']}, "
            f"next_start={final_result['next_start_id']}"
        )
        return final_result

    def _record_cancelled(self, img_id: int) -> None:
        """把一个任务计入取消桶并推进进度。"""
        with self._lock:
            self._completed_count += 1
            self._cancelled_ids.append(img_id)
            current = self._completed_count
        self.progress_signal.emit(current, f"取消 {img_id}")

    def _record_cancelled_batch(self, img_ids: List[int]) -> None:
        """把一批任务计入取消桶，只发一次进度信号。

        大批量取消（可达数千个未启动任务）逐个发跨线程信号会瞬间灌满
        GUI 事件队列，让界面在按下停止后反而卡顿。
        """
        if not img_ids:
            return
        with self._lock:
            self._completed_count += len(img_ids)
            self._cancelled_ids.extend(img_ids)
            current = self._completed_count
        self.progress_signal.emit(current, f"已取消 {len(img_ids)} 个任务")

    def _handle_finished_future(self, future, img_id: int,
                                task: DownloadTask) -> None:
        """汇总一个已结束 future 的结果（成功/失败/取消）。"""
        try:
            if future.cancelled():
                self._record_cancelled(img_id)
                return
            success = bool(future.result())
        except Exception as exc:
            logger.error(
                f"[request_id={self.request_id}] download task exception: {exc}",
                exc_info=True,
            )
            success = False

        # 成功优先：文件已完整落盘的任务即使赶上取消也算成功。
        if not success and task.was_cancelled:
            self._record_cancelled(img_id)
            return

        with self._lock:
            self._completed_count += 1
            if success:
                self._success_count += 1
                self._success_ids.append(img_id)
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

    def _build_final_result(self, initially_completed_ids: Set[int],
                            records_saved: Optional[bool] = None,
                            persist_checkpoint: bool = True) -> dict:
        """Calculate and persist the contiguous continuation checkpoint.

        Only verified current files and successful files from this run count.
        Historical download records do not prove that a file still exists.
        The initial disk scan is reused; this run's successes went through
        atomic_replace + integrity checks, so no second full scan is needed.

        persist_checkpoint=False is the crash-fallback mode: statistics only,
        no config.json write, and checkpoint_saved reported False so the UI
        does not claim a clean save for a crashed run.
        """
        completed_ids = set(initially_completed_ids)
        completed_ids.update(self._success_ids)
        # 本次已尝试且失败记录成功落盘的 ID 也算"已处理"：否则范围内一个
        # 永久失效的 ID（如服务器已删除）会把续传点永远卡在原地，之后每次
        # 都"从头开始"。失败 ID 保留在记录里并已提示 UI，可手动重试；
        # 记录没写成功时不越过失败项，避免失败信息彻底丢失。
        handled_ids = set(completed_ids)
        if records_saved:
            handled_ids.update(self._fail_ids)
        request_end = self.start_id + self.count
        resume_id = self.start_id
        while resume_id < request_end and resume_id in handled_ids:
            resume_id += 1

        last_contiguous_id = resume_id - 1 if resume_id > self.start_id else None
        persisted_last_id = Config.get_last_downloaded_id()
        checkpoint_saved = persist_checkpoint
        checkpoint_advanced = False

        if persist_checkpoint and last_contiguous_id is not None:
            # Do not cross an unverified gap before the manually selected range.
            # Advance the global checkpoint only when all intervening IDs were
            # handled (verified on disk, or attempted and recorded failed).
            global_gap_start = persisted_last_id + 1
            intervening_ids_complete = all(
                img_id in handled_ids
                for img_id in range(global_gap_start, last_contiguous_id + 1)
            )
            if intervening_ids_complete:
                previous_persisted_id = persisted_last_id
                checkpoint_saved, persisted_last_id = (
                    Config.advance_last_downloaded_id(last_contiguous_id)
                )
                checkpoint_advanced = (
                    checkpoint_saved and persisted_last_id > previous_persisted_id
                )

        global_next_start_id = persisted_last_id + 1
        return {
            "success": not self.cancelled,
            "success_count": self._success_count,
            "fail_count": self._fail_count,
            "fail_ids": self._fail_ids,
            "cancelled_ids": self._cancelled_ids,
            "success_ids": self._success_ids,
            "total": self.count,
            "cancelled": self.cancelled,
            "skipped": self._skipped_ids,
            "partial_files_cleaned": self._partial_files_cleaned,
            "records_saved": records_saved,
            "last_contiguous_id": last_contiguous_id,
            "resume_id": resume_id,
            "checkpoint_saved": checkpoint_saved,
            "checkpoint_advanced": checkpoint_advanced,
            "last_downloaded_id": persisted_last_id,
            "next_start_id": global_next_start_id,
            "global_next_start_id": global_next_start_id,
        }

    # ------------------------------------------------------------------
    # Control interface
    # ------------------------------------------------------------------
    def cancel_download(self):
        """请求取消下载（只置标志，立即返回）。

        future 的撤销、取消记账和 .part 清理全部由 worker 线程在主循环里
        完成：在调用方线程（GUI）删除 .part 会与仍在写盘的任务竞争，把一次
        完整有效的下载变成失败。应用退出时由 ThumbnailDownloader.shutdown
        负责 join 本线程。
        """
        self.cancelled = True
