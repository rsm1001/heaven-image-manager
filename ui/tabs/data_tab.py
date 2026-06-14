"""数据管理选项卡模块"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QPushButton, QTextEdit, QTableWidget,
    QHeaderView, QMessageBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from pathlib import Path
import sys
import random
import logging
from datetime import datetime

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
from utils.config import Config
from core.file_manager import FileManager
from ui.sortable_item import SortableTableItem

logger = logging.getLogger("HeavenComic")

# 数据表的列定义: (列索引, sort_kind)
_TABLE_COLUMNS = [
    (0, "str"),       # 名称
    (1, "str"),       # 来源
    (2, "str"),       # 扩展名
    (3, "datetime"),  # 添加时间(YYYY-MM-DD HH:MM:SS,文本序即时间序)
]


class DataTabWidget(QWidget):
    """数据管理选项卡组件"""

    def __init__(self, parent_widget):
        """初始化选项卡

        Args:
            parent_widget: 父组件引用（ManagerWidget）
        """
        super().__init__()
        self.parent_widget = parent_widget
        self.current_random_item = None
        self._create_ui()

    def _create_ui(self):
        """创建UI"""
        layout = QVBoxLayout(self)

        # 随机获取组
        random_group = QGroupBox("随机获取")
        random_layout = QVBoxLayout(random_group)

        random_buttons_layout = QHBoxLayout()
        self.random_button = QPushButton("随机获取一个项目")
        self.random_button.clicked.connect(self._on_get_random_item)

        self.delete_current_button = QPushButton("删除当前显示的项目")
        self.delete_current_button.clicked.connect(self._on_delete_current_item)

        self.clear_display_button = QPushButton("清空显示")
        self.clear_display_button.clicked.connect(self._on_clear_display)

        random_buttons_layout.addWidget(self.random_button)
        random_buttons_layout.addWidget(self.delete_current_button)
        random_buttons_layout.addWidget(self.clear_display_button)
        random_buttons_layout.addStretch()

        # 显示区域
        self.random_result_text = QTextEdit()
        self.random_result_text.setMaximumHeight(150)
        self.random_result_text.setReadOnly(True)

        random_layout.addLayout(random_buttons_layout)
        random_layout.addWidget(self.random_result_text)

        # 数据表格
        table_group = QGroupBox("JSON数据表格")
        table_layout = QVBoxLayout(table_group)

        self.data_table = QTableWidget()
        self.data_table.setColumnCount(len(_TABLE_COLUMNS))
        self.data_table.setHorizontalHeaderLabels(["名称", "来源", "扩展名", "添加时间"])
        header = self.data_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)

        # 排序状态:默认按"添加时间"倒序,最符合直觉
        self._sort_col = 3
        self._sort_order = Qt.DescendingOrder
        self.data_table.setSortingEnabled(True)
        self.data_table.sortByColumn(self._sort_col, self._sort_order)
        header.sortIndicatorChanged.connect(self._on_sort_changed)

        # 按钮行
        table_buttons_layout = QHBoxLayout()
        self.reload_table_button = QPushButton("刷新表格")
        self.reload_table_button.clicked.connect(self._on_load_table_data)

        self.clear_json_button = QPushButton("清空JSON文件")
        self.clear_json_button.clicked.connect(self._on_clear_json_file)

        self.open_trash_button = QPushButton("🗑️ 垃圾桶")
        self.open_trash_button.clicked.connect(self._on_open_trash)

        table_buttons_layout.addWidget(self.reload_table_button)
        table_buttons_layout.addWidget(self.clear_json_button)
        table_buttons_layout.addStretch()
        table_buttons_layout.addWidget(self.open_trash_button)

        table_layout.addLayout(table_buttons_layout)
        table_layout.addWidget(self.data_table)

        layout.addWidget(random_group)
        layout.addWidget(table_group)

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

    def _show_result_info(self):
        """检查是否需要显示结果信息"""
        main_window = self._find_main_window()
        if main_window and hasattr(main_window, 'get_confirmation_setting'):
            return main_window.get_confirmation_setting()
        return True

    def _on_load_table_data(self):
        """加载表格数据"""
        data = FileManager.load_json_data()

        # 灌数据期间关闭排序,避免每 setItem 一次就触发一次重排
        self.data_table.setSortingEnabled(False)
        try:
            self.data_table.setRowCount(len(data))
            for row, item in enumerate(data):
                for col_index, sort_kind in _TABLE_COLUMNS:
                    field = item.get({
                        0: "name",
                        1: "source",
                        2: "extension",
                        3: "added_time",
                    }[col_index], "")
                    self.data_table.setItem(
                        row, col_index,
                        SortableTableItem(str(field), sort_kind=sort_kind),
                    )
        finally:
            self.data_table.setSortingEnabled(True)

        # 还原用户当前选择的排序方式
        self.data_table.sortByColumn(self._sort_col, self._sort_order)

    def _on_sort_changed(self, column: int, order):
        """用户点击表头时记录当前排序方式,刷新后能继续保留"""
        if column < 0:
            return
        self._sort_col = column
        self._sort_order = order

    def _on_get_random_item(self):
        """随机获取项目"""
        logger.info("随机获取项目")
        data = FileManager.load_json_data()

        if not data:
            self.random_result_text.setPlainText("JSON文件中没有数据")
            self.current_random_item = None
            logger.warning("JSON文件为空，无法随机选择")
            return

        self.current_random_item = random.choice(data)

        formatted_lines = []
        for key, value in self.current_random_item.items():
            formatted_lines.append(f"{key}: {value}")

        self.random_result_text.setPlainText("\n".join(formatted_lines))
        logger.info(f"已随机选择项目: {self.current_random_item.get('name', '未知')}")

    def _on_delete_current_item(self):
        """删除当前项目

        业务主键：name（与 JsonStorage.append_items 去重逻辑保持一致）。
        不再做"全字段 == 匹配"，避免 added_time 变化或 current_random_item
        携带 UI 临时键导致漏删/误删。
        """
        if not self.current_random_item:
            QMessageBox.warning(self, "警告", "请先随机获取一个项目")
            return

        target_name = self.current_random_item.get("name")
        if not target_name:
            QMessageBox.warning(self, "警告", "当前项目缺少 name 字段，无法定位")
            return

        confirmation_needed = self._get_confirmation_setting()

        # 先按 name 主键定位数据中真实存在的行
        data = FileManager.load_json_data()
        actual_rows = [item for item in data if item.get("name") == target_name]
        if not actual_rows:
            QMessageBox.information(
                self, "提示",
                f"数据中已不存在 name='{target_name}' 的项目（可能已被其他操作删除）"
            )
            self.current_random_item = None
            self.random_result_text.setPlainText("项目已不存在")
            return

        if confirmation_needed:
            preview_str = "\n".join([f"{k}: {v}" for k, v in actual_rows[0].items()])
            reply = QMessageBox.question(
                self, "确认删除",
                f"确定要从JSON中删除以下项目吗？\n\n{preview_str}",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
        else:
            reply = QMessageBox.Yes

        if reply == QMessageBox.Yes:
            logger.info(f"开始删除项目: name={target_name}")
            # 用数据里的真实行作为 undo 记录，避免 current_random_item 含临时键
            deleted_item = dict(actual_rows[0])

            # 按 name 主键过滤后保存
            json_path = Config.COMIC_DIR / "image_names.json"
            new_data = [item for item in FileManager.load_json_data()
                        if item.get("name") != target_name]
            if FileManager.save_json_data(new_data, json_path):
                # 记录删除操作历史
                FileManager.push_undo({
                    "type": "delete_item",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "data": {"item": deleted_item, "json_path": str(json_path)}
                })
                self._update_undo_button_state()

                if self._show_result_info():
                    QMessageBox.information(self, "成功", "项目已删除")

                self.current_random_item = None
                self.random_result_text.setPlainText("项目已删除")
                self._on_load_table_data()
                self.parent_widget.update_stats()
                logger.info("项目删除成功")
            else:
                QMessageBox.critical(self, "错误", "删除失败")
                logger.error("项目删除失败")

    def _on_clear_display(self):
        """清空显示"""
        self.random_result_text.setPlainText("")
        self.current_random_item = None

    def _on_clear_json_file(self):
        """清空JSON文件"""
        data = FileManager.load_json_data()
        if not data:
            QMessageBox.information(self, "提示", "JSON文件已经为空")
            return

        confirmation_needed = self._get_confirmation_setting()

        if confirmation_needed:
            reply = QMessageBox.question(
                self, "确认清空",
                "确定要清空JSON文件中的所有数据吗？\n此操作不可撤销！",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
        else:
            reply = QMessageBox.Yes

        if reply == QMessageBox.Yes:
            if FileManager.save_json_data([]):
                if self._show_result_info():
                    QMessageBox.information(self, "成功", "JSON文件已清空")
                self._on_load_table_data()
                self.parent_widget.update_stats()
                logger.info("JSON文件已清空")
            else:
                QMessageBox.critical(self, "错误", "清空JSON文件失败")
                logger.error("清空JSON文件失败")

    def _on_open_trash(self):
        """打开垃圾桶"""
        from ui.trash_widget import TrashWidget
        trash_dialog = TrashWidget(self.parent_widget)
        trash_dialog.exec_()


def create_data_tab(parent_widget) -> QWidget:
    """创建数据管理选项卡（工厂函数）

    Args:
        parent_widget: 父组件引用

    Returns:
        QWidget: 创建的选项卡组件
    """
    return DataTabWidget(parent_widget)
