"""图片预览组件"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QMessageBox, QFrame, QSizePolicy, QScrollArea
)
from PyQt5.QtGui import QPixmap, QPainter, QColor
from PyQt5.QtCore import Qt, QSize
from pathlib import Path
import random
import sys
from datetime import datetime
from pathlib import Path
# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.file_manager import FileManager
from core.image_processor import ImageProcessor
from utils.config import Config
from utils.logger import logger
from .fullscreen_window import FullScreenWindow


class PreviewWidget(QWidget):
    """图片预览组件"""
    
    def __init__(self):
        super().__init__()
        self.current_index = -1
        self.image_files = []
        self.current_pixmap = None
        
        self.init_ui()
        self.load_images()
    
    def init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # 顶部控制面板
        control_layout = QHBoxLayout()
        control_layout.setSpacing(0)
        control_layout.setContentsMargins(0, 0, 0, 0)
        
        self.prev_button = QPushButton("上一张")
        self.prev_button.clicked.connect(self.show_prev_image)
        
        self.next_button = QPushButton("下一张")
        self.next_button.clicked.connect(self.show_next_image)
        
        self.move_button = QPushButton("移动到101目录")
        self.move_button.clicked.connect(self.move_current_image)
        
        self.delete_button = QPushButton("删除图片")
        self.delete_button.clicked.connect(self.delete_current_image)
        
        self.random_button = QPushButton("随机图片")
        self.random_button.clicked.connect(self.show_random_image)
        
        self.refresh_button = QPushButton("刷新")
        self.refresh_button.clicked.connect(lambda: self.on_refresh_button_clicked())

        self.fullscreen_button = QPushButton("全屏")
        self.fullscreen_button.clicked.connect(self.show_fullscreen)

        control_layout.addWidget(self.prev_button)
        control_layout.addWidget(self.next_button)
        control_layout.addWidget(self.move_button)
        control_layout.addWidget(self.delete_button)
        control_layout.addWidget(self.random_button)
        control_layout.addWidget(self.refresh_button)
        control_layout.addWidget(self.fullscreen_button)
        control_layout.addStretch()
        
        layout.addLayout(control_layout)
        
        # 图片显示区域
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignCenter)
        
        # 创建图片标签
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.image_label.setMinimumSize(1, 1)
        
        self.scroll_area.setWidget(self.image_label)
        
        # 添加到布局
        layout.addWidget(self.scroll_area)
        
        # 底部信息栏
        info_layout = QHBoxLayout()
        info_layout.setSpacing(0)
        info_layout.setContentsMargins(0, 0, 0, 0)
        
        self.info_label = QLabel("就绪")
        self.info_label.setStyleSheet("font-size: 12px; color: gray;")
        
        self.counter_label = QLabel("0/0")
        self.counter_label.setStyleSheet("font-size: 12px; color: gray;")
        
        info_layout.addWidget(self.info_label)
        info_layout.addStretch()
        info_layout.addWidget(self.counter_label)
        
        layout.addLayout(info_layout)
        
        # 设置快捷键
        self.setFocusPolicy(Qt.StrongFocus)
        
        self.update_controls()
        logger.info("PreviewWidget initialized")
    
    def load_images(self):
        """加载图片列表"""
        self.image_files = FileManager.get_image_files()
        self.current_index = -1 if not self.image_files else 0
        self.update_counter()
        self.update_controls()
        
        if self.image_files:
            self.show_current_image()
        else:
            self.image_label.clear()
            self.info_label.setText("comic目录中没有找到图片文件")
    
    def _normalize_index(self) -> bool:
        """把 current_index 修正到合法区间。空列表返回 False。"""
        total = len(self.image_files)
        if total == 0:
            self.current_index = -1
            return False
        if self.current_index < 0:
            self.current_index = 0
        elif self.current_index >= total:
            self.current_index = total - 1
        return True

    def show_current_image(self):
        """显示当前图片。

        损坏图自动删除时不再递归调用自身，而是用 while 循环推进，避免连续
        损坏图导致栈溢出。同时保证 current_index 始终落在合法区间，避免
        末尾 +1 后被取模跳回 0 的"跳图"现象。
        """
        # 最多连续处理 N 张坏图（N 与列表长度一致即可），超过即视作环境异常
        max_attempts = max(1, len(self.image_files))

        for _ in range(max_attempts):
            if not self._normalize_index():
                self.image_label.clear()
                self.info_label.setText("没有图片可显示")
                self.update_counter()
                self.update_controls()
                return

            image_path = self.image_files[self.current_index]

            # 加载并显示图片
            pixmap = ImageProcessor.load_and_resize_image(image_path)

            if pixmap:
                self.current_pixmap = pixmap
                self.image_label.setPixmap(pixmap)
                self.image_label.adjustSize()

                # 更新图片信息
                image_info = ImageProcessor.get_image_info(image_path)
                self.info_label.setText(f"{image_path.name} - {image_info}")
                self.update_counter()
                self.update_controls()
                return

            # 加载失败：自动删除损坏文件
            self.image_label.clear()
            self.info_label.setText(f"无法加载图片: {image_path.name}")
            success, _ = FileManager.delete_image(image_path)
            if success:
                logger.info(f"已自动删除损坏图片: {image_path.name}")
                # 列表就地删除
                if 0 <= self.current_index < len(self.image_files):
                    del self.image_files[self.current_index]
            else:
                # 删除也失败：跳过当前张继续往后
                logger.warning(f"损坏图片删除失败，跳过: {image_path.name}")
                self.current_index += 1

            # 重新进入循环前做一次边界修正；list 已空则在 normalize 中清空
            if not self._normalize_index():
                self.image_label.clear()
                self.info_label.setText("所有图片已处理完成")
                self.update_counter()
                self.update_controls()
                return

        # 超过最大尝试次数仍未找到好图（极端情况：连续多张坏图又删不掉）
        self.image_label.clear()
        self.info_label.setText("无法显示任何图片")
        self.update_counter()
        self.update_controls()

    def show_next_image(self):
        """显示下一张图片"""
        if not self.image_files:
            return
        
        # 过滤掉已被删除的文件
        self.image_files = [f for f in self.image_files if f.exists()]
        
        if not self.image_files:
            self.image_label.clear()
            self.info_label.setText("所有图片已处理完成")
            self.current_index = -1
            self.update_counter()
            self.update_controls()
            return
        
        # 更新索引
        self.current_index = (self.current_index + 1) % len(self.image_files)
        self.show_current_image()
    
    def show_prev_image(self):
        """显示上一张图片"""
        if not self.image_files:
            return
        
        # 过滤掉已被删除的文件
        self.image_files = [f for f in self.image_files if f.exists()]
        
        if not self.image_files:
            self.image_label.clear()
            self.info_label.setText("没有图片")
            self.current_index = -1
            self.update_counter()
            self.update_controls()
            return
        
        # 更新索引
        self.current_index = (self.current_index - 1) % len(self.image_files)
        self.show_current_image()
    
    def show_random_image(self):
        """显示随机图片"""
        if not self.image_files:
            return
        
        # 过滤掉已被删除的文件
        self.image_files = [f for f in self.image_files if f.exists()]
        
        if not self.image_files:
            self.image_label.clear()
            self.info_label.setText("没有图片")
            self.current_index = -1
            self.update_counter()
            self.update_controls()
            return
        
        # 随机选择一个索引
        if len(self.image_files) > 0:
            self.current_index = random.randint(0, len(self.image_files) - 1)
            self.show_current_image()
    
    def move_current_image(self):
        """移动当前图片"""
        if not self.image_files or self.current_index < 0 or self.current_index >= len(self.image_files):
            return

        image_path = self.image_files[self.current_index]

        if not image_path.exists():
            self.info_label.setText("图片文件不存在")
            self.show_next_image()
            return

        # 移动文件
        success, message, target_path = FileManager.move_image(image_path)

        # 获取主窗口中的二次确认设置，决定是否显示结果信息
        # 逐级查找父窗口直到找到MainWindow
        parent_widget = self
        main_window = None
        while parent_widget:
            if type(parent_widget).__name__ == 'MainWindow':
                main_window = parent_widget
                break
            parent_widget = parent_widget.parent()

        # 检查是否需要显示确认信息
        show_result_info = True
        if main_window and hasattr(main_window, 'get_confirmation_setting'):
            # 如果二次确认被关闭，我们也减少信息提示
            show_result_info = main_window.get_confirmation_setting()
        else:
            show_result_info = True  # 默认显示

        if show_result_info:
            QMessageBox.information(self, "移动结果", message)

        self.info_label.setText(message)

        # 更新列表
        if success:
            FileManager.push_undo({
                "type": "move",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "data": {"source": str(image_path), "target": str(target_path)}
            })
            if main_window:
                main_window.update_undo_button_state()
            del self.image_files[self.current_index]
            if self.image_files:
                if self.current_index >= len(self.image_files):
                    self.current_index = max(0, len(self.image_files) - 1)
            else:
                self.current_index = -1
                self.image_label.clear()

        self.show_next_image()
    
    def delete_current_image(self):
        """删除当前图片"""
        if not self.image_files or self.current_index < 0 or self.current_index >= len(self.image_files):
            return

        image_path = self.image_files[self.current_index]

        if not image_path.exists():
            self.info_label.setText("图片文件不存在")
            self.show_next_image()
            return

        # 获取主窗口中的二次确认设置
        # 逐级查找父窗口直到找到MainWindow
        parent_widget = self
        main_window = None
        while parent_widget:
            if type(parent_widget).__name__ == 'MainWindow':
                main_window = parent_widget
                break
            parent_widget = parent_widget.parent()

        if main_window and hasattr(main_window, 'get_confirmation_setting'):
            confirmation_needed = main_window.get_confirmation_setting()
        else:
            confirmation_needed = True  # 默认需要确认

        if confirmation_needed:
            # 确认删除
            reply = QMessageBox.question(
                self, '确认删除',
                f'确定要删除图片 "{image_path.name}" 吗？',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
        else:
            # 直接删除，不显示确认对话框
            reply = QMessageBox.Yes

        if reply == QMessageBox.Yes:
            # 删除文件
            success, message = FileManager.delete_image(image_path)

            # 获取主窗口中的二次确认设置，决定是否显示结果信息
            # 逐级查找父窗口直到找到MainWindow
            parent_widget = self
            main_window = None
            while parent_widget:
                if type(parent_widget).__name__ == 'MainWindow':
                    main_window = parent_widget
                    break
                parent_widget = parent_widget.parent()

            # 检查是否需要显示确认信息
            show_result_info = True
            if main_window and hasattr(main_window, 'get_confirmation_setting'):
                # 这里我们反转逻辑，如果二次确认被关闭，我们认为用户不希望看到太多提示
                show_result_info = main_window.get_confirmation_setting()  # 如果设置了二次确认，则显示结果信息
            else:
                show_result_info = True  # 默认显示

            if show_result_info:
                QMessageBox.information(self, "删除结果", message)

            self.info_label.setText(message)

            # 更新列表
            if success:
                FileManager.push_undo({
                    "type": "delete",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "data": {"name": image_path.stem, "original_path": str(image_path.relative_to(Config.COMIC_DIR))}
                })
                if main_window:
                    main_window.update_undo_button_state()
                del self.image_files[self.current_index]
                if self.image_files:
                    if self.current_index >= len(self.image_files):
                        self.current_index = max(0, len(self.image_files) - 1)
                else:
                    self.current_index = -1
                    self.image_label.clear()

            self.show_next_image()
    
    def update_counter(self):
        """更新计数器"""
        total = len(self.image_files)
        if total == 0:
            self.counter_label.setText("0/0")
            self.current_index = -1
        else:
            if self.current_index < 0:
                self.current_index = 0
            elif self.current_index >= total:
                self.current_index = total - 1
            
            current = self.current_index + 1
            self.counter_label.setText(f"{current}/{total}")
    
    def update_controls(self):
        """更新控件状态"""
        has_images = bool(self.image_files)
        has_valid_index = (0 <= self.current_index < len(self.image_files)) if self.image_files else False

        self.prev_button.setEnabled(has_images)
        self.next_button.setEnabled(has_images)
        self.move_button.setEnabled(has_valid_index)
        self.delete_button.setEnabled(has_valid_index)
        self.random_button.setEnabled(has_images)
        self.fullscreen_button.setEnabled(has_valid_index)

    def on_refresh_button_clicked(self):
        """刷新按钮点击处理"""
        self.refresh(reload=True)

    def show_fullscreen(self):
        """显示全屏预览"""
        if not self.image_files or self.current_index < 0:
            return

        self.fullscreen_window = FullScreenWindow(self.image_files, self.current_index, self)
        self.fullscreen_window.exec_()
        # 关闭后更新当前索引
        self.current_index = self.fullscreen_window.current_index
        self.update_counter()
        self.update_controls()

    def refresh(self, reload=True):
        """刷新

        Args:
            reload: 是否重新加载文件列表并重置位置，False只刷新列表保持当前位置
        """
        if reload:
            self.load_images()
        else:
            # 只重新加载文件列表，保持当前索引位置
            self.image_files = FileManager.get_image_files()
            # 确保 current_index 有效
            if self.image_files:
                if self.current_index < 0:
                    self.current_index = 0
                elif self.current_index >= len(self.image_files):
                    self.current_index = len(self.image_files) - 1
                self.show_current_image()
            else:
                self.current_index = -1
                self.image_label.clear()
                self.info_label.setText("comic目录中没有找到图片文件")
            self.update_counter()
            self.update_controls()
    
    def resizeEvent(self, event):
        """调整大小事件"""
        super().resizeEvent(event)
        if self.current_pixmap:
            # 重新显示当前图片以适应新尺寸
            self.show_current_image()