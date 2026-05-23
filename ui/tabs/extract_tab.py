"""文件提取选项卡模块"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QGroupBox, QLineEdit, QPushButton, QTextEdit,
    QRadioButton, QButtonGroup, QCheckBox, QMessageBox
)
from PyQt5.QtCore import Qt
from datetime import datetime
from pathlib import Path
import sys
import logging

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
from utils.config import Config
from core.file_manager import FileManager

logger = logging.getLogger("HeavenComic")


class ExtractTabWidget(QWidget):
    """文件提取选项卡组件"""

    # 信号定义
    extract_completed = None  # 可扩展为信号
    refresh_requested = None  # 可扩展为信号

    def __init__(self, parent_widget):
        """初始化选项卡

        Args:
            parent_widget: 父组件引用（ManagerWidget）
        """
        super().__init__()
        self.parent_widget = parent_widget
        self._create_ui()

    def _create_ui(self):
        """创建UI"""
        layout = QVBoxLayout(self)

        # 源目录选择组
        source_group = QGroupBox("源目录设置")
        source_layout = QFormLayout(source_group)

        self.source_dir_input = QLineEdit()
        self.source_dir_input.setText(str(Config.COMIC_DIR / "101"))
        browse_button = QPushButton("浏览...")
        browse_button.clicked.connect(self._on_browse_source_dir)

        source_hbox = QHBoxLayout()
        source_hbox.addWidget(self.source_dir_input)
        source_hbox.addWidget(browse_button)
        source_layout.addRow("源目录:", source_hbox)

        # 模式选择组
        mode_group = QGroupBox("处理模式")
        mode_layout = QVBoxLayout(mode_group)

        self.mode_group = QButtonGroup()
        self.append_radio = QRadioButton("追加模式 (保留原有数据，添加新数据)")
        self.append_radio.setChecked(True)
        self.overwrite_radio = QRadioButton("覆盖模式 (清空原有数据，重新添加)")

        self.mode_group.addButton(self.append_radio)
        self.mode_group.addButton(self.overwrite_radio)
        mode_layout.addWidget(self.append_radio)
        mode_layout.addWidget(self.overwrite_radio)

        # 删除选项组
        delete_group = QGroupBox("提取后处理")
        delete_layout = QVBoxLayout(delete_group)
        self.delete_after_checkbox = QCheckBox("提取完成后删除源文件（不经过垃圾桶，直接删除）")
        delete_layout.addWidget(self.delete_after_checkbox)

        # 操作按钮
        button_layout = QHBoxLayout()
        self.extract_button = QPushButton("开始提取")
        self.extract_button.clicked.connect(self._on_extract_images)
        self.refresh_button = QPushButton("刷新统计")
        self.refresh_button.clicked.connect(self._on_refresh_requested)
        button_layout.addWidget(self.extract_button)
        button_layout.addWidget(self.refresh_button)
        button_layout.addStretch()

        # 日志区域
        log_group = QGroupBox("操作日志")
        log_layout = QVBoxLayout(log_group)
        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(200)
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)

        # 添加到主布局
        layout.addWidget(source_group)
        layout.addWidget(mode_group)
        layout.addWidget(delete_group)
        layout.addLayout(button_layout)
        layout.addWidget(log_group)
        layout.addStretch()

    def _find_main_window(self):
        """查找主窗口"""
        widget = self.parent_widget
        while widget:
            if type(widget).__name__ == 'MainWindow':
                return widget
            widget = widget.parent()
        return None

    def _get_confirmation_setting(self):
        """获取二次确认设置"""
        main_window = self._find_main_window()
        if main_window and hasattr(main_window, 'get_confirmation_setting'):
            return main_window.get_confirmation_setting()
        return True

    def _update_undo_button_state(self):
        """更新撤销按钮状态"""
        main_window = self._find_main_window()
        if main_window:
            main_window.update_undo_button_state()

    def _log_message(self, message):
        """记录日志消息"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")

    def _on_browse_source_dir(self):
        """浏览源目录"""
        from PyQt5.QtWidgets import QFileDialog

        initial_dir = Config.COMIC_DIR / "101"
        if not initial_dir.exists():
            initial_dir = Config.COMIC_DIR

        dir_path = QFileDialog.getExistingDirectory(
            self, "选择包含图片的目录", str(initial_dir)
        )

        if dir_path:
            self.source_dir_input.setText(dir_path)
            self._log_message(f"选择目录: {dir_path}")

    def _on_refresh_requested(self):
        """刷新请求处理"""
        self.parent_widget.refresh()

    def _on_extract_images(self):
        """提取图片处理"""
        source_dir = self.source_dir_input.text().strip()
        if not source_dir:
            QMessageBox.warning(self, "警告", "请输入源目录路径")
            return

        append_mode = self.append_radio.isChecked()
        delete_after_extract = self.delete_after_checkbox.isChecked()
        mode_text = "追加" if append_mode else "覆盖"
        delete_text = "，删除源文件" if delete_after_extract else ""

        full_path = Path(source_dir)
        if not full_path.is_absolute():
            full_path = Config.BASE_DIR / source_dir

        confirmation_needed = self._get_confirmation_setting()

        # 确认操作
        confirm_msg = f"这将提取目录中的图片名称:\n{full_path}\n\n"
        if append_mode:
            confirm_msg += "模式: 追加（保留原有数据，添加新数据）\n"
        else:
            confirm_msg += "模式: 覆盖（清空原有数据，重新添加）\n"
        if delete_after_extract:
            confirm_msg += "注意: 提取完成后将直接删除源文件（不经过垃圾桶）！\n"
        confirm_msg += "\n确定要继续吗？"

        if confirmation_needed:
            reply = QMessageBox.question(
                self, "确认操作", confirm_msg,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
        else:
            reply = QMessageBox.Yes

        if reply != QMessageBox.Yes:
            self._log_message("用户取消操作")
            return

        logger.info(f"开始提取图片，目录: {full_path}，模式: {mode_text}")
        self._log_message(f"开始处理目录: {full_path}，模式: {mode_text}{delete_text}")

        # 执行提取
        result = FileManager.extract_image_names_from_directory(
            full_path, append_mode, delete_after_extract
        )

        if result["success"]:
            # 记录提取操作历史
            FileManager.push_undo({
                "type": "extract",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "data": {
                    "added_items": result.get("added_items", []),
                    "json_path": str(Config.COMIC_DIR / "image_names.json")
                }
            })
            self._update_undo_button_state()
            QMessageBox.information(self, "成功", result["message"])
            self._log_message(f"操作成功: {result['message']}")
        else:
            QMessageBox.critical(self, "错误", result["message"])
            self._log_message(f"操作失败: {result['message']}")

        self.parent_widget.refresh()


def create_extract_tab(parent_widget) -> QWidget:
    """创建文件提取选项卡（工厂函数）

    Args:
        parent_widget: 父组件引用

    Returns:
        QWidget: 创建的选项卡组件
    """
    return ExtractTabWidget(parent_widget)
