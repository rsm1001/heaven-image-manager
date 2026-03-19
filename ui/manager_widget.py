"""图片管理组件"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QLineEdit, QTextEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QRadioButton, QButtonGroup, QFileDialog, QMessageBox,
    QProgressBar, QTabWidget, QFormLayout
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
from pathlib import Path
import random
import json
from datetime import datetime
import sys
from pathlib import Path
# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.file_manager import FileManager
from utils.config import Config
from utils.logger import logger


class ManagerWidget(QWidget):
    """图片管理组件"""
    
    def __init__(self):
        super().__init__()
        self.current_random_item = None
        
        self.init_ui()
        self.refresh()
    
    def init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout(self)
        
        # 创建选项卡
        tab_widget = QTabWidget()
        
        # 文件提取选项卡
        extract_tab = self.create_extract_tab()
        tab_widget.addTab(extract_tab, "文件提取")
        
        # 数据管理选项卡
        data_tab = self.create_data_tab()
        tab_widget.addTab(data_tab, "数据管理")
        
        # 统计信息选项卡
        stats_tab = self.create_stats_tab()
        tab_widget.addTab(stats_tab, "统计信息")
        
        layout.addWidget(tab_widget)
    
    def create_extract_tab(self):
        """创建文件提取选项卡"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 源目录选择组
        source_group = QGroupBox("源目录设置")
        source_layout = QFormLayout(source_group)
        
        self.source_dir_input = QLineEdit()
        self.source_dir_input.setText(str(Config.COMIC_DIR / "101"))
        browse_button = QPushButton("浏览...")
        browse_button.clicked.connect(self.browse_source_dir)
        
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
        
        # 操作按钮
        button_layout = QHBoxLayout()
        
        self.extract_button = QPushButton("开始提取")
        self.extract_button.clicked.connect(self.extract_images)
        
        self.refresh_button = QPushButton("刷新统计")
        self.refresh_button.clicked.connect(self.refresh)
        
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
        layout.addLayout(button_layout)
        layout.addWidget(log_group)
        layout.addStretch()
        
        return widget
    
    def create_data_tab(self):
        """创建数据管理选项卡"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # 随机获取组
        random_group = QGroupBox("随机获取")
        random_layout = QVBoxLayout(random_group)
        
        random_buttons_layout = QHBoxLayout()
        
        self.random_button = QPushButton("随机获取一个项目")
        self.random_button.clicked.connect(self.get_random_item)
        
        self.delete_current_button = QPushButton("删除当前显示的项目")
        self.delete_current_button.clicked.connect(self.delete_current_item)
        
        self.clear_display_button = QPushButton("清空显示")
        self.clear_display_button.clicked.connect(self.clear_display)
        
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
        self.data_table.setColumnCount(4)
        self.data_table.setHorizontalHeaderLabels(["名称", "来源", "扩展名", "添加时间"])
        header = self.data_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        
        # 按钮行
        table_buttons_layout = QHBoxLayout()
        
        self.reload_table_button = QPushButton("刷新表格")
        self.reload_table_button.clicked.connect(self.load_table_data)
        
        self.clear_json_button = QPushButton("清空JSON文件")
        self.clear_json_button.clicked.connect(self.clear_json_file)
        
        table_buttons_layout.addWidget(self.reload_table_button)
        table_buttons_layout.addWidget(self.clear_json_button)
        table_buttons_layout.addStretch()
        
        table_layout.addLayout(table_buttons_layout)
        table_layout.addWidget(self.data_table)
        
        layout.addWidget(random_group)
        layout.addWidget(table_group)
        
        return widget
    
    def create_stats_tab(self):
        """创建统计信息选项卡"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
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
        refresh_button.clicked.connect(self.update_stats)
        refresh_layout.addWidget(refresh_button)
        refresh_layout.addStretch()
        
        layout.addWidget(stats_group)
        layout.addLayout(refresh_layout)
        layout.addStretch()
        
        return widget
    
    def browse_source_dir(self):
        """浏览源目录"""
        initial_dir = Config.COMIC_DIR / "101"
        if not initial_dir.exists():
            initial_dir = Config.COMIC_DIR
        
        dir_path = QFileDialog.getExistingDirectory(
            self, "选择包含图片的目录", str(initial_dir)
        )
        
        if dir_path:
            self.source_dir_input.setText(dir_path)
            self.log_message(f"选择目录: {dir_path}")
    
    def extract_images(self):
        """提取图片"""
        source_dir = self.source_dir_input.text().strip()
        if not source_dir:
            QMessageBox.warning(self, "警告", "请输入源目录路径")
            return
        
        append_mode = self.append_radio.isChecked()
        mode_text = "追加" if append_mode else "覆盖"
        
        full_path = Path(source_dir)
        if not full_path.is_absolute():
            full_path = Config.BASE_DIR / source_dir
        
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
        
        # 确认操作
        confirm_msg = f"这将提取目录中的图片名称:\n{full_path}\n\n"
        if append_mode:
            confirm_msg += "模式: 追加（保留原有数据，添加新数据）\n"
        else:
            confirm_msg += "模式: 覆盖（清空原有数据，重新添加）\n"
        confirm_msg += "\n确定要继续吗？"
        
        if confirmation_needed:
            reply = QMessageBox.question(
                self, "确认操作", confirm_msg,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
        else:
            # 直接执行，不显示确认对话框
            reply = QMessageBox.Yes
        
        if reply != QMessageBox.Yes:
            self.log_message("用户取消操作")
            return
        
        self.log_message(f"开始处理目录: {full_path}，模式: {mode_text}")
        
        # 执行提取
        result = FileManager.extract_image_names_from_directory(
            full_path, append_mode
        )
        
        if result["success"]:
            QMessageBox.information(self, "成功", result["message"])
            self.log_message(f"操作成功: {result['message']}")
        else:
            QMessageBox.critical(self, "错误", result["message"])
            self.log_message(f"操作失败: {result['message']}")
        
        self.refresh()
    
    def get_random_item(self):
        """随机获取项目"""
        self.log_message("随机获取项目...")
        data = FileManager.load_json_data()
        
        if not data:
            self.random_result_text.setPlainText("JSON文件中没有数据")
            self.current_random_item = None
            self.log_message("JSON文件为空，无法随机选择")
            return
        
        self.current_random_item = random.choice(data)
        
        # 格式化显示
        formatted_lines = []
        for key, value in self.current_random_item.items():
            formatted_lines.append(f"{key}: {value}")
        
        self.random_result_text.setPlainText("\n".join(formatted_lines))
        self.log_message(f"已随机选择项目: {self.current_random_item.get('name', '未知')}")
    
    def delete_current_item(self):
        """删除当前项目"""
        if not self.current_random_item:
            QMessageBox.warning(self, "警告", "请先随机获取一个项目")
            self.log_message("删除失败: 未选择项目")
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
        
        # 确认删除
        item_str = "\n".join([f"{k}: {v}" for k, v in self.current_random_item.items()])
        
        if confirmation_needed:
            reply = QMessageBox.question(
                self, "确认删除",
                f"确定要从JSON中删除以下项目吗？\n\n{item_str}",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
        else:
            # 直接删除，不显示确认对话框
            reply = QMessageBox.Yes
        
        if reply == QMessageBox.Yes:
            self.log_message(f"开始删除项目: {self.current_random_item.get('name', '未知')}")
            
            # 从数据中移除该项目
            data = FileManager.load_json_data()
            new_data = []
            
            for item in data:
                # 比较所有键值对
                match = True
                for key, value in self.current_random_item.items():
                    if key not in item or item[key] != value:
                        match = False
                        break
                
                if not match:
                    new_data.append(item)
            
            # 保存更新后的数据
            if FileManager.save_json_data(new_data):
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
                    QMessageBox.information(self, "成功", "项目已删除")
                    
                self.current_random_item = None
                self.random_result_text.setPlainText("项目已删除")
                self.load_table_data()
                self.update_stats()
                self.log_message("项目删除成功")
            else:
                QMessageBox.critical(self, "错误", "删除失败")
                self.log_message("项目删除失败")
        else:
            self.log_message("用户取消删除操作")
    
    def clear_display(self):
        """清空显示"""
        self.random_result_text.setPlainText("")
        self.current_random_item = None
        self.log_message("显示区域已清空")
    
    def clear_json_file(self):
        """清空JSON文件"""
        data = FileManager.load_json_data()
        if not data:
            QMessageBox.information(self, "提示", "JSON文件已经为空")
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
            reply = QMessageBox.question(
                self, "确认清空",
                "确定要清空JSON文件中的所有数据吗？\n此操作不可撤销！",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
        else:
            # 直接清空，不显示确认对话框
            reply = QMessageBox.Yes
        
        if reply == QMessageBox.Yes:
            if FileManager.save_json_data([]):
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
                    QMessageBox.information(self, "成功", "JSON文件已清空")
                    
                self.load_table_data()
                self.update_stats()
                self.log_message("JSON文件已清空")
            else:
                QMessageBox.critical(self, "错误", "清空JSON文件失败")
                self.log_message("清空JSON文件失败")
    
    def load_table_data(self):
        """加载表格数据"""
        data = FileManager.load_json_data()
        
        self.data_table.setRowCount(len(data))
        
        for row, item in enumerate(data):
            self.data_table.setItem(row, 0, QTableWidgetItem(str(item.get("name", ""))))
            self.data_table.setItem(row, 1, QTableWidgetItem(str(item.get("source", ""))))
            self.data_table.setItem(row, 2, QTableWidgetItem(str(item.get("extension", ""))))
            self.data_table.setItem(row, 3, QTableWidgetItem(str(item.get("added_time", ""))))
    
    def update_stats(self):
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
    
    def log_message(self, message):
        """记录日志消息"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
    
    def refresh(self):
        """刷新所有数据"""
        self.update_stats()
        self.load_table_data()
        self.log_message("数据已刷新")
        logger.info("ManagerWidget refreshed")