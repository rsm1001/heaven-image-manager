"""下载管理器模块"""
import os
import time
import json
import requests
import urllib3
from pathlib import Path
from typing import List, Dict, Callable, Optional, Set
from concurrent.futures import ThreadPoolExecutor, as_completed
from PyQt5.QtCore import QThread, pyqtSignal
import sys
import threading
from datetime import datetime
# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.config import Config
from utils.logger import logger


# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 默认线程数
DEFAULT_MAX_WORKERS = 5

# 全局线程池（进程内单例）
_thread_pool = None
_pool_lock = threading.Lock()


def get_download_pool(max_workers: int = DEFAULT_MAX_WORKERS) -> ThreadPoolExecutor:
    """获取或创建全局下载线程池"""
    global _thread_pool
    with _pool_lock:
        if _thread_pool is None:
            _thread_pool = ThreadPoolExecutor(max_workers=max_workers)
        return _thread_pool


def shutdown_download_pool():
    """关闭全局线程池（应用退出时调用）"""
    global _thread_pool
    with _pool_lock:
        if _thread_pool is not None:
            _thread_pool.shutdown(wait=True)
            _thread_pool = None


class DownloadRecord:
    """下载记录管理器"""

    @staticmethod
    def load_records() -> Dict[int, dict]:
        """加载下载记录"""
        if not Config.DOWNLOAD_RECORD_FILE.exists():
            return {}
        try:
            with open(Config.DOWNLOAD_RECORD_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return {int(k): v for k, v in data.items()}
        except Exception as e:
            logger.error(f"Failed to load download records: {e}")
            return {}

    @staticmethod
    def save_records(records: Dict[int, dict]) -> bool:
        """保存下载记录（超过上限时清理旧记录）"""
        if len(records) > Config.MAX_DOWNLOAD_RECORD_COUNT:
            # 按时间排序，优先删除失败记录，再删除最早的成功记录
            sorted_ids = sorted(
                records.keys(),
                key=lambda x: (
                    0 if records[x].get("status") == "failed" else 1,
                    records[x].get("downloaded_time", "") or records[x].get("failed_time", "")
                )
            )
            # 保留最新的 MAX_DOWNLOAD_RECORD_COUNT 条
            keep_ids = set(sorted_ids[-Config.MAX_DOWNLOAD_RECORD_COUNT:])
            records = {k: v for k, v in records.items() if k in keep_ids}
            logger.info(f"Download records trimmed to {len(records)} entries")

        try:
            with open(Config.DOWNLOAD_RECORD_FILE, 'w', encoding='utf-8') as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to save download records: {e}")
            return False

    @staticmethod
    def get_completed_ids() -> Set[int]:
        """获取已成功下载的ID集合"""
        records = DownloadRecord.load_records()
        return {img_id for img_id, rec in records.items() if rec.get("status") == "success"}

    @staticmethod
    def get_existing_file_ids() -> Set[int]:
        """扫描已存在的图片文件ID"""
        existing_ids = set()
        for ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']:
            for p in Config.COMIC_DIR.glob(f"*{ext}"):
                try:
                    existing_ids.add(int(p.stem))
                except ValueError:
                    pass
        return existing_ids


class DownloadWorker(QThread):
    """下载工作线程（使用线程池并行下载）"""
    progress_signal = pyqtSignal(int, str)  # (current, status)
    completed_signal = pyqtSignal(dict)     # 结果字典
    status_signal = pyqtSignal(str)        # 状态更新

    def __init__(self, start_id: int, count: int, max_workers: int = DEFAULT_MAX_WORKERS):
        super().__init__()
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
        self._fail_ids = []
        self._success_ids = []
        self._skipped_ids: List[int] = []
        self._download_records: Dict[int, dict] = {}

    def run(self):
        """执行下载任务（线程池并行模式）"""
        self.is_running = True
        self._completed_count = 0
        self._success_count = 0
        self._fail_count = 0
        self._fail_ids = []
        self._success_ids = []
        self._skipped_ids = []
        self._active_futures = []
        self._download_records = DownloadRecord.load_records()

        # 扫描已存在的文件和已成功下载的记录
        existing_file_ids = DownloadRecord.get_existing_file_ids()
        completed_ids = DownloadRecord.get_completed_ids()
        skip_ids = existing_file_ids | completed_ids

        # 计算本次实际需要下载的ID列表
        target_ids = []
        for i in range(self.count):
            img_id = self.start_id + i
            if img_id in skip_ids:
                self._skipped_ids.append(img_id)
            else:
                target_ids.append(img_id)

        self.status_signal.emit(f"开始下载：从{self.start_id}开始，共{self.count}张（并行{self.max_workers}线程，已跳过{len(self._skipped_ids)}张）")
        logger.info(f"Starting parallel download: {self.start_id}, count: {self.count}, max_workers: {self.max_workers}, skip {len(self._skipped_ids)}")

        if not target_ids:
            self.status_signal.emit("所有图片已存在或已下载，无需重复下载")
            self.completed_signal.emit({
                "success": True,
                "success_count": 0,
                "fail_count": 0,
                "fail_ids": [],
                "total": self.count,
                "cancelled": False,
                "skipped": self._skipped_ids
            })
            self.is_running = False
            return

        pool = get_download_pool(self.max_workers)

        # 1. 提交所有下载任务到线程池
        for img_id in target_ids:
            if self.cancelled:
                break
            future = pool.submit(self._download_task, img_id)
            self._active_futures.append(future)

        # 2. 等待所有任务完成（使用as_completed实现实时反馈）
        futures_snapshot = list(self._active_futures)

        for future in as_completed(futures_snapshot):
            if self.cancelled:
                for f in futures_snapshot:
                    if not f.done():
                        f.cancel()
                break

            try:
                result = future.result()
                img_id, success = result

                with self._lock:
                    self._completed_count += 1
                    if success:
                        self._success_count += 1
                        self._success_ids.append(img_id)
                        self._download_records[img_id] = {
                            "status": "success",
                            "downloaded_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "file_size": (Config.COMIC_DIR / f"{img_id}.jpg").stat().st_size if (Config.COMIC_DIR / f"{img_id}.jpg").exists() else 0
                        }
                    else:
                        self._fail_count += 1
                        self._fail_ids.append(img_id)
                        self._download_records[img_id] = {
                            "status": "failed",
                            "failed_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                    current = self._completed_count

                self.progress_signal.emit(current, f"{'成功' if success else '失败'} {img_id}")

            except Exception as e:
                logger.error(f"Download task exception: {e}")

        # 3. 保存下载记录
        DownloadRecord.save_records(self._download_records)

        # 4. 发射完成信号
        final_result = {
            "success": not self.cancelled,
            "success_count": self._success_count,
            "fail_count": self._fail_count,
            "fail_ids": self._fail_ids,
            "success_ids": self._success_ids,
            "total": self.count,
            "cancelled": self.cancelled,
            "skipped": self._skipped_ids
        }

        self.completed_signal.emit(final_result)
        self.is_running = False
        logger.info(f"Download completed: success={self._success_count}, fail={self._fail_count}, skipped={len(self._skipped_ids)}")

    def _download_task(self, img_id: int) -> tuple:
        """线程池中执行的下载任务（每个ID独立运行）"""
        proxies = {
            "http": os.getenv("PROXY_HTTP", "http://127.0.0.1:7897"),
            "https": os.getenv("PROXY_HTTPS", "http://127.0.0.1:7897")
        }

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://18comic.vip/"
        }

        # 代理重试逻辑在每个线程内部独立处理
        for proxy_retry in range(Config.PROXY_RETRY_TIMES):
            if self.cancelled:
                return (img_id, False)

            if self._do_download(img_id, proxies, headers):
                logger.info(f"Successfully downloaded image {img_id}")
                return (img_id, True)
            else:
                if not self.cancelled and proxy_retry < Config.PROXY_RETRY_TIMES - 1:
                    self.status_signal.emit(f"[{img_id}] 代理重试 {proxy_retry + 1}/{Config.PROXY_RETRY_TIMES}...")
                    time.sleep(Config.PROXY_RETRY_DELAY)

        logger.warning(f"Failed to download image {img_id}")
        return (img_id, False)

    def _do_download(self, img_id: int, proxies: dict, headers: dict) -> bool:
        """单次下载尝试"""
        if self.cancelled:
            return False

        img_url = Config.BASE_URL.format(img_id)
        save_path = Config.COMIC_DIR / f"{img_id}.jpg"

        for retry in range(Config.RETRY_TIMES):
            if self.cancelled:
                return False

            try:
                response = requests.get(
                    img_url,
                    proxies=proxies,
                    headers=headers,
                    timeout=20,
                    verify=False,
                    stream=True
                )
                response.raise_for_status()

                with open(save_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=1024):
                        if self.cancelled:
                            return False
                        if chunk:
                            f.write(chunk)

                # 下载成功后添加小延迟，避免过快（可调整或移除）
                time.sleep(Config.REQUEST_DELAY)
                return True
            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code
                if status_code in [502, 503, 504]:
                    if not self.cancelled:
                        time.sleep(Config.RETRY_DELAY)
                        continue
                logger.error(f"HTTP Error {status_code} for image {img_id}")
                break
            except requests.exceptions.RequestException as e:
                logger.error(f"Request error for image {img_id}: {str(e)}")
                if not self.cancelled:
                    time.sleep(Config.RETRY_DELAY)
                    continue
                break
            except Exception as e:
                logger.error(f"Unknown error for image {img_id}: {str(e)}")
                break

        return False

    def cancel_download(self):
        """取消下载"""
        self.cancelled = True
        with self._lock:
            for f in self._active_futures:
                f.cancel()
        self.wait(3000)


class ThumbnailDownloader:
    """缩略图下载器类"""

    def __init__(self):
        self.worker = None

    def start_download(self, start_id: int, count: int,
                      progress_callback: Callable = None,
                      completed_callback: Callable = None,
                      status_callback: Callable = None,
                      max_workers: int = DEFAULT_MAX_WORKERS):
        """开始下载"""
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
        logger.info(f"Started download worker: start_id={start_id}, count={count}, max_workers={max_workers}")
        return True

    def cancel_download(self):
        """取消下载"""
        if self.worker and self.worker.is_running:
            self.worker.cancel_download()
            logger.info("Cancelled download")