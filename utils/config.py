"""配置管理模块"""
import os
from pathlib import Path


class Config:
    """配置类"""
    # 项目根目录
    BASE_DIR = Path(__file__).parent.parent
    
    # 图片扩展名
    IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
    
    # 目录配置
    COMIC_DIR = BASE_DIR / "comic"
    TARGET_DIR = COMIC_DIR / "101"
    
    # 窗口配置
    WINDOW_TITLE = "天堂图片管理器 - PyQt版"
    WINDOW_WIDTH = 1000
    WINDOW_HEIGHT = 700
    
    # 图片显示配置
    MAX_IMAGE_WIDTH = 800
    MAX_IMAGE_HEIGHT = 500
    
    # 下载配置
    START_ID = 9009
    TOTAL_COUNT = 450
    RETRY_TIMES = 3
    RETRY_DELAY = 15
    REQUEST_DELAY = 2
    PROXY_RETRY_TIMES = 10
    PROXY_RETRY_DELAY = 20
    BASE_URL = "https://cdn-msp.18comic.vip/media/albums/{}.jpg?u=1682391243"
    
    @classmethod
    def ensure_directories(cls):
        """确保必要目录存在"""
        cls.COMIC_DIR.mkdir(parents=True, exist_ok=True)
        cls.TARGET_DIR.mkdir(parents=True, exist_ok=True)


# 确保目录存在
Config.ensure_directories()