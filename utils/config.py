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
    # 将窗口宽度和高度设为原来基础上放大2倍后，再取四分之三（即原来的1.5倍）
    WINDOW_WIDTH = 1500
    WINDOW_HEIGHT = 1050
    # 屏幕居中标志（True表示启动时位于屏幕中央）
    CENTER_ON_SCREEN = True
    
    # 图片显示配置
    # 原来是MAX_IMAGE_WIDTH = 800, MAX_IMAGE_HEIGHT = 500
    # 放大1.5倍后是：
    MAX_IMAGE_WIDTH = 1200
    MAX_IMAGE_HEIGHT = 750
    
    # 下载配置
    # 起始ID：批量下载的起始编号
    START_ID = 9009
    # 总数：需要下载的图片总数
    TOTAL_COUNT = 450
    # 重试次数：单次下载失败后的重试次数
    RETRY_TIMES = 3
    # 重试延迟：重试前的延迟时间（秒）
    RETRY_DELAY = 15
    # 请求延迟：每次请求之间的延迟时间（秒），避免过于频繁的请求
    REQUEST_DELAY = 2
    # 代理重试次数：使用代理下载时的重试次数
    PROXY_RETRY_TIMES = 10
    # 代理重试延迟：代理重试前的延迟时间（秒）
    PROXY_RETRY_DELAY = 20
    # 基础URL：图片下载的基础URL模板，{}会被替换为图片ID
    BASE_URL = "https://cdn-msp.18comic.vip/media/albums/{}.jpg?u=1682391243"
    
    @classmethod
    def ensure_directories(cls):
        """确保必要目录存在"""
        cls.COMIC_DIR.mkdir(parents=True, exist_ok=True)
        cls.TARGET_DIR.mkdir(parents=True, exist_ok=True)


# 确保目录存在
Config.ensure_directories()