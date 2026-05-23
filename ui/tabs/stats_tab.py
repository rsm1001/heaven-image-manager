"""统计信息选项卡模块"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QLabel, QPushButton
)
from PyQt5.QtGui import QFont
from pathlib import Path
import sys

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
from core.file_manager import FileManager


class StatsTabWidget(QWidget):
    """统计信息选项卡组件"""

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

        # 统计信息显示
        stats_group = QGroupBox("数据统计")
        stats_layout = QGridLayout(stats_group)

        self.stats_labels = {}

        labels = [
            ("json_exists_label", "JSON文件存在: "),
            ("item_count_label", "项目数量: "),
            ("file_size_label", "文件大小: "),
            ("first_added_label", "最早添加: "),
            ("last_added_label", "最新添加: ")
        ]

        row = 0
        for obj_name, text in labels:
            label = QLabel(text)
            value_label = QLabel("--")
            value_label.setFont(QFont("Consolas", 10))
            self.stats_labels[obj_name] = value_label
            stats_layout.addWidget(label, row, 0)
            stats_layout.addWidget(value_label, row, 1)
            row += 1

        # 刷新按钮
        refresh_layout = QHBoxLayout()
        refresh_button = QPushButton("刷新统计")
        refresh_button.clicked.connect(self._on_update_stats)
        refresh_layout.addWidget(refresh_button)
        refresh_layout.addStretch()

        layout.addWidget(stats_group)
        layout.addLayout(refresh_layout)
        layout.addStretch()

    def _on_update_stats(self):
        """更新统计信息"""
        stats = FileManager.get_stats()

        if stats["file_exists"]:
            self.stats_labels["json_exists_label"].setText("是")
            self.stats_labels["item_count_label"].setText(str(stats["item_count"]))
            self.stats_labels["file_size_label"].setText(f"{stats['file_size_kb']:.2f} KB")
            if 'first_added' in stats:
                self.stats_labels["first_added_label"].setText(stats["first_added"])
            if 'last_added' in stats:
                self.stats_labels["last_added_label"].setText(stats["last_added"])
        else:
            self.stats_labels["json_exists_label"].setText("否")
            self.stats_labels["item_count_label"].setText("0")
            self.stats_labels["file_size_label"].setText("0.00 KB")
            self.stats_labels["first_added_label"].setText("--")
            self.stats_labels["last_added_label"].setText("--")


def create_stats_tab(parent_widget) -> QWidget:
    """创建统计信息选项卡（工厂函数）

    Args:
        parent_widget: 父组件引用

    Returns:
        QWidget: 创建的选项卡组件
    """
    return StatsTabWidget(parent_widget)
