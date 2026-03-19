"""图像处理模块"""
from pathlib import Path
from typing import Optional, Tuple
from PIL import Image
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtCore import QSize
import io
import sys
from pathlib import Path
# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.config import Config
from utils.logger import logger


class ImageProcessor:
    """图片处理类"""
    
    @staticmethod
    def load_and_resize_image(image_path: Path) -> Optional[QPixmap]:
        """加载并调整图片大小以适应显示区域"""
        try:
            # 使用PIL打开图片
            img = Image.open(image_path)
            
            # 计算缩放比例
            width_ratio = Config.MAX_IMAGE_WIDTH / img.width
            height_ratio = Config.MAX_IMAGE_HEIGHT / img.height
            scale_ratio = min(width_ratio, height_ratio)  # 移除1.0的限制，允许放大图片
            
            if scale_ratio != 1.0:  # 只有当需要缩放时才调整
                new_width = int(img.width * scale_ratio)
                new_height = int(img.height * scale_ratio)
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # 将PIL图像转换为QPixmap
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='PNG')
            img_byte_arr.seek(0)
            
            # 创建QImage
            qimg = QImage.fromData(img_byte_arr.getvalue())
            pixmap = QPixmap.fromImage(qimg)
            
            return pixmap
        except Exception as e:
            logger.error(f"Failed to load image {image_path}: {e}")
            return None
    
    @staticmethod
    def get_image_info(image_path: Path) -> str:
        """获取图片信息"""
        try:
            with Image.open(image_path) as img:
                size_kb = image_path.stat().st_size // 1024
                return f"尺寸: {img.width}×{img.height}, 大小: {size_kb}KB"
        except Exception as e:
            logger.error(f"Failed to get image info for {image_path}: {e}")
            return "无法获取图片信息"
    
    @staticmethod
    def calculate_scale_factor(original_width: int, original_height: int, 
                             max_width: int, max_height: int) -> float:
        """计算缩放因子"""
        width_ratio = max_width / original_width
        height_ratio = max_height / original_height
        return min(width_ratio, height_ratio)  # 移除1.0的限制，允许放大图片
    
    @staticmethod
    def resize_pixmap(pixmap: QPixmap, max_size: QSize) -> QPixmap:
        """按比例缩放QPixmap"""
        # 允许放大或缩小图片
        return pixmap.scaled(
            max_size,
            aspectRatioMode=1,  # KeepAspectRatio
            transformMode=1     # SmoothTransformation
        )