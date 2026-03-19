"""下载管理器模块"""
import os
import time
import requests
import urllib3
from pathlib import Path
from typing import List, Dict, Callable
from PyQt5.QtCore import QThread, pyqtSignal
import sys
from pathlib import Path
# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.config import Config
from utils.logger import logger


# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class DownloadWorker(QThread):
    """下载工作线程"""
    progress_signal = pyqtSignal(int, str)  # (current, status)
    completed_signal = pyqtSignal(dict)     # 结果字典
    status_signal = pyqtSignal(str)         # 状态更新

    def __init__(self, start_id: int, count: int):
        super().__init__()
        self.start_id = start_id
        self.count = count
        self.is_running = False
        self.cancelled = False

    def run(self):
        """执行下载任务"""
        self.is_running = True
        success_count, fail_count, fail_ids = 0, 0, []
        
        self.status_signal.emit(f"开始下载：从{self.start_id}开始，共{self.count}张")
        logger.info(f"Starting download: {self.start_id}, count: {self.count}")

        # 代理配置
        proxies = {
            "http": os.getenv("PROXY_HTTP", "http://127.0.0.1:7897"),
            "https": os.getenv("PROXY_HTTPS", "http://127.0.0.1:7897")
        }

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://18comic.vip/"
        }

        for i in range(self.count):
            if self.cancelled:
                break
                
            img_id = self.start_id + i
            self.progress_signal.emit(i + 1, f"下载 {img_id}...")

            # 代理重试机制
            downloaded = False
            for proxy_retry in range(Config.PROXY_RETRY_TIMES):
                if self.download_single_image(img_id, proxies, headers):
                    logger.info(f"Successfully downloaded image {img_id}")
                    success_count += 1
                    downloaded = True
                    break  # 成功则跳出代理重试循环
                else:
                    if not self.cancelled and proxy_retry < Config.PROXY_RETRY_TIMES - 1:  # 不是最后一次重试
                        self.status_signal.emit(f"代理重试 {proxy_retry + 1}/{Config.PROXY_RETRY_TIMES}...")
                        time.sleep(Config.PROXY_RETRY_DELAY)
                    else:
                        logger.warning(f"Failed to download image {img_id}")
                        fail_count += 1
                        fail_ids.append(img_id)

            if not self.cancelled:
                time.sleep(Config.REQUEST_DELAY)

        result = {
            "success": not self.cancelled,
            "success_count": success_count,
            "fail_count": fail_count,
            "fail_ids": fail_ids,
            "total": self.count,
            "cancelled": self.cancelled
        }
        
        self.completed_signal.emit(result)
        self.is_running = False

    def download_single_image(self, img_id: int, proxies: dict, headers: dict) -> bool:
        """下载单张图片（带重试）"""
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
        self.wait()


class ThumbnailDownloader:
    """缩略图下载器类"""
    
    def __init__(self):
        self.worker = None
    
    def start_download(self, start_id: int, count: int, 
                      progress_callback: Callable = None,
                      completed_callback: Callable = None,
                      status_callback: Callable = None):
        """开始下载"""
        if self.worker and self.worker.isRunning():
            logger.warning("Download already in progress")
            return False
        
        self.worker = DownloadWorker(start_id, count)
        
        if progress_callback:
            self.worker.progress_signal.connect(progress_callback)
        if completed_callback:
            self.worker.completed_signal.connect(completed_callback)
        if status_callback:
            self.worker.status_signal.connect(status_callback)
        
        self.worker.start()
        logger.info(f"Started download worker: start_id={start_id}, count={count}")
        return True
    
    def cancel_download(self):
        """取消下载"""
        if self.worker and self.worker.is_running:
            self.worker.cancel_download()
            logger.info("Cancelled download")