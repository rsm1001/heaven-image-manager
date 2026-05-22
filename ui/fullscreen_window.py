"""全屏预览与幻灯片窗口"""
from PyQt5.QtWidgets import QDialog, QLabel, QVBoxLayout
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt, QTimer, QEvent
from PyQt5.QtCore import pyqtSignal
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.config import Config
from utils.logger import logger


class FullScreenWindow(QDialog):
    """全屏预览与幻灯片窗口"""

    closed = pyqtSignal(int)

    def __init__(self, image_files, start_index, parent=None):
        super().__init__(parent)
        self.image_files = image_files
        self.current_index = start_index

        # 无边框全屏窗口
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setStyleSheet("background-color: black;")

        # 全屏显示
        self.showFullScreen()

        # 布局：图片占满剩余空间，info条固定底部
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 图片标签
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background-color: black;")
        layout.addWidget(self.image_label, stretch=1)

        # 信息条
        self.info_label = QLabel()
        self.info_label.setAlignment(Qt.AlignCenter)
        self.info_label.setFixedHeight(40)
        self.info_label.setStyleSheet(
            "color: white; background-color: rgba(0, 0, 0, 200);"
            "padding: 0 20px; border: none;"
        )
        layout.addWidget(self.info_label)

        # 幻灯片定时器
        self.slide_timer = QTimer(self)
        self.slide_timer.timeout.connect(self._slide_next)
        self.slide_timer.start(Config.SLIDE_INTERVAL_MS)

        # 安装事件过滤器
        self.installEventFilter(self)

        # 延迟激活窗口
        QTimer.singleShot(100, self._activate_and_show)

        logger.info(f"FullScreenWindow opened at index {start_index}")

    def _activate_and_show(self):
        """激活窗口并显示图片"""
        self.activateWindow()
        self.raise_()
        self.setFocusPolicy(Qt.StrongFocus)
        self.setFocus()
        self._show_current_image()

    def _show_current_image(self):
        """显示当前图片"""
        if not self.image_files or self.current_index < 0 or self.current_index >= len(self.image_files):
            self.image_label.clear()
            self.info_label.setText("没有图片")
            return

        image_path = self.image_files[self.current_index]
        pixmap = QPixmap(str(image_path))

        if not pixmap.isNull():
            scaled = self._scale_to_available(pixmap)
            self.image_label.setPixmap(scaled)
            self._update_info()
        else:
            self.image_label.setPixmap(QPixmap())
            self.info_label.setText(f"无法加载图片: {image_path.name}")

    def _scale_to_available(self, pixmap):
        """基于窗口可用区域缩放图片"""
        # 用窗口尺寸减去信息条高度作为可用区域
        avail_h = self.height() - 40
        avail_w = self.width()

        if avail_w <= 0 or avail_h <= 0:
            return pixmap

        pw, ph = pixmap.width(), pixmap.height()
        if pw == 0 or ph == 0:
            return pixmap

        ratio = min(avail_w / pw, avail_h / ph)
        new_w, new_h = int(pw * ratio), int(ph * ratio)

        return pixmap.scaled(new_w, new_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    def _update_info(self, suffix=""):
        """更新信息条"""
        if not self.image_files or self.current_index < 0:
            return
        path = self.image_files[self.current_index]
        total = len(self.image_files)
        cur = self.current_index + 1
        self.info_label.setText(
            f"  {cur}/{total} - {path.name}  |  ← → 翻页  |  空格 暂停/继续  |  ESC 退出  {suffix}"
        )

    def _slide_next(self):
        """幻灯片自动翻页"""
        if not self.image_files:
            return
        self.image_files = [f for f in self.image_files if f.exists()]
        if not self.image_files:
            self.slide_timer.stop()
            return
        self.current_index = (self.current_index + 1) % len(self.image_files)
        self._show_current_image()

    def show_next(self):
        if not self.image_files:
            return
        self.image_files = [f for f in self.image_files if f.exists()]
        if not self.image_files:
            return
        self.current_index = (self.current_index + 1) % len(self.image_files)
        self._show_current_image()

    def show_prev(self):
        if not self.image_files:
            return
        self.image_files = [f for f in self.image_files if f.exists()]
        if not self.image_files:
            return
        self.current_index = (self.current_index - 1) % len(self.image_files)
        self._show_current_image()

    def toggle_slideshow(self):
        if self.slide_timer.isActive():
            self.slide_timer.stop()
            self._update_info(suffix="[已暂停]")
        else:
            self.slide_timer.start(Config.SLIDE_INTERVAL_MS)
            self._update_info()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress:
            k = event.key()
            if k == Qt.Key_Escape:
                self.close()
                return True
            elif k == Qt.Key_Left:
                self.show_prev()
                return True
            elif k == Qt.Key_Right:
                self.show_next()
                return True
            elif k == Qt.Key_Space:
                self.toggle_slideshow()
                return True
        return super().eventFilter(obj, event)

    def closeEvent(self, event):
        self.slide_timer.stop()
        self.closed.emit(self.current_index)
        logger.info(f"FullScreenWindow closed at index {self.current_index}")
        event.accept()
