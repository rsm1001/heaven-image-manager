"""配置管理模块"""
import os
import json
from pathlib import Path


class Config:
    """配置类 - 统一管理所有配置"""

    # 项目根目录
    BASE_DIR = Path(__file__).parent.parent

    # 图片扩展名
    IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}

    # 目录配置
    COMIC_DIR = BASE_DIR / "comic"
    TARGET_DIR = COMIC_DIR / "101"

    # 窗口配置
    WINDOW_TITLE = "天堂图片管理器 - PyQt版"
    WINDOW_WIDTH = 900
    WINDOW_HEIGHT = 700
    CENTER_ON_SCREEN = True

    # 图片显示配置
    MAX_IMAGE_WIDTH = 800
    MAX_IMAGE_HEIGHT = 550
    SLIDE_INTERVAL_MS = 3000

    # 下载配置
    DEFAULT_START_ID = 9009  # SpinBox 默认起始ID的 fallback 值
    DEFAULT_LAST_DOWNLOADED_ID = 9008  # config.json 读取失败时的默认值
    TOTAL_COUNT = 450
    RETRY_TIMES = 3
    RETRY_DELAY = 15
    REQUEST_DELAY = 2
    PROXY_RETRY_TIMES = 10
    PROXY_RETRY_DELAY = 20
    MAX_DOWNLOAD_WORKERS = 5
    BASE_URL = "https://cdn-msp.18comic.vip/media/albums/{}.jpg?u=1682391243"

    # 垃圾桶配置
    TRASH_DIR = COMIC_DIR / "trash"
    TRASH_RECORD_FILE = COMIC_DIR / "trash_records.json"
    MAX_TRASH_COUNT = 1000

    # 下载记录配置
    DOWNLOAD_RECORD_FILE = COMIC_DIR / "download_records.json"
    MAX_DOWNLOAD_RECORD_COUNT = 5000

    # config.json 路径
    CONFIG_FILE = BASE_DIR / "config.json"

    @classmethod
    def ensure_directories(cls):
        """确保必要目录存在"""
        cls.COMIC_DIR.mkdir(parents=True, exist_ok=True)
        cls.TARGET_DIR.mkdir(parents=True, exist_ok=True)
        cls.TRASH_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def get_last_downloaded_id(cls) -> int:
        """从 config.json 读取 last_downloaded_id，失败时返回默认值"""
        try:
            with open(cls.CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f).get('last_downloaded_id', cls.DEFAULT_LAST_DOWNLOADED_ID)
        except (FileNotFoundError, json.JSONDecodeError):
            return cls.DEFAULT_LAST_DOWNLOADED_ID

    @classmethod
    def set_last_downloaded_id(cls, value: int):
        """写入 config.json 的 last_downloaded_id"""
        try:
            with open(cls.CONFIG_FILE, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            config_data = {}
        config_data['last_downloaded_id'] = value
        with open(cls.CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=4)


# 确保目录存在
Config.ensure_directories()