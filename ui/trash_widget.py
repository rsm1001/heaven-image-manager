"""垃圾桶组件"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QHeaderView, QMessageBox, QGroupBox, QDialog
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
import sys
from pathlib import Path
# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.file_manager import FileManager
from utils.config import Config
from utils.logger import logger


class TrashWidget(QDialog):
    """垃圾桶窗口"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("垃圾桶")
        self.setGeometry(300, 200, 700, 450)
        self.init_ui()
        self.load_data()
    
    def init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout(self)
        
        # 统计信息
        self.stats_label = QLabel("就绪")
        self.stats_label.setStyleSheet("color: gray; padding: 5px;")
        layout.addWidget(self.stats_label)
        
        # 表格
        table_group = QGroupBox("已删除图片")
        table_layout = QVBoxLayout(table_group)
        
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["名称", "原始位置", "删除时间", "文件大小"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setColumnWidth(0, 200)
        self.table.setColumnWidth(2, 140)
        self.table.setColumnWidth(3, 80)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.MultiSelection)
        self.table.itemSelectionChanged.connect(self.update_button_states)
        
        table_layout.addWidget(self.table)
        
        # 按钮行
        button_layout = QHBoxLayout()
        
        self.restore_button = QPushButton("恢复选中")
        self.restore_button.clicked.connect(self.restore_selected)
        
        self.permanent_delete_button = QPushButton("永久删除选中")
        self.permanent_delete_button.clicked.connect(self.permanent_delete_selected)
        
        self.empty_button = QPushButton("清空全部")
        self.empty_button.clicked.connect(self.empty_trash)
        
        self.refresh_button = QPushButton("刷新")
        self.refresh_button.clicked.connect(self.load_data)
        
        button_layout.addWidget(self.restore_button)
        button_layout.addWidget(self.permanent_delete_button)
        button_layout.addWidget(self.empty_button)
        button_layout.addStretch()
        button_layout.addWidget(self.refresh_button)
        
        table_layout.addLayout(button_layout)
        
        layout.addWidget(table_group)
        
        # 底部说明
        note_label = QLabel("提示：恢复图片将放回原始位置，如原位置文件已存在则自动重命名")
        note_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(note_label)
    
    def load_data(self):
        """加载数据"""
        records = FileManager.get_trash_records()
        
        self.table.setRowCount(len(records))
        
        for row, record in enumerate(records):
            name = record.get("name", "")
            original_path = record.get("original_path", "")
            deleted_time = record.get("deleted_time", "")
            file_size = record.get("file_size", 0)
            
            # 格式化文件大小
            if file_size:
                size_str = self._format_size(file_size)
            else:
                size_str = "--"
            
            self.table.setItem(row, 0, QTableWidgetItem(name))
            self.table.setItem(row, 1, QTableWidgetItem(original_path))
            self.table.setItem(row, 2, QTableWidgetItem(deleted_time))
            self.table.setItem(row, 3, QTableWidgetItem(size_str))
        
        # 更新统计
        total_size = sum(r.get("file_size", 0) for r in records)
        self.stats_label.setText(
            f"共 {len(records)} 张图片，总计 {self._format_size(total_size)}，"
            f"最大容量 {Config.MAX_TRASH_COUNT} 张"
        )
        
        self.update_button_states()
        logger.info(f"TrashWidget loaded {len(records)} records")
    
    def _format_size(self, size: int) -> str:
        """格式化文件大小"""
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        else:
            return f"{size / (1024 * 1024 * 1024):.1f} GB"
    
    def update_button_states(self):
        """更新按钮状态"""
        has_selection = len(self.table.selectedItems()) > 0
        has_data = self.table.rowCount() > 0
        
        self.restore_button.setEnabled(has_selection)
        self.permanent_delete_button.setEnabled(has_selection)
        self.empty_button.setEnabled(has_data)
    
    def get_selected_names(self) -> list:
        """获取选中的图片名称"""
        names = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.isSelected():
                names.append(item.text())
        return names
    
    def restore_selected(self):
        """恢复选中的图片"""
        names = self.get_selected_names()
        if not names:
            QMessageBox.warning(self, "警告", "请先选择要恢复的图片")
            return
        
        # 确认恢复
        if len(names) == 1:
            msg = f"确定要恢复图片 \"{names[0]}\" 吗？"
        else:
            msg = f"确定要恢复选中的 {len(names)} 张图片吗？"
        
        reply = QMessageBox.question(self, "确认恢复", msg,
                                      QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        
        if reply != QMessageBox.Yes:
            return
        
        success_count = 0
        fail_count = 0
        fail_names = []
        
        for name in names:
            success, msg = FileManager.restore_from_trash(name)
            if success:
                success_count += 1
            else:
                fail_count += 1
                fail_names.append(f"{name}: {msg}")
        
        # 显示结果
        if fail_count == 0:
            QMessageBox.information(self, "成功", f"已成功恢复 {success_count} 张图片")
        else:
            QMessageBox.warning(self, "部分失败",
                              f"成功恢复 {success_count} 张，失败 {fail_count} 张\n\n" +
                              "\n".join(fail_names))
        
        self.load_data()
    
    def permanent_delete_selected(self):
        """永久删除选中的图片"""
        names = self.get_selected_names()
        if not names:
            QMessageBox.warning(self, "警告", "请先选择要永久删除的图片")
            return
        
        # 确认删除
        if len(names) == 1:
            msg = f"确定要永久删除图片 \"{names[0]}\" 吗？此操作不可撤销！"
        else:
            msg = f"确定要永久删除选中的 {len(names)} 张图片吗？此操作不可撤销！"
        
        reply = QMessageBox.question(self, "确认永久删除", msg,
                                      QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        
        if reply != QMessageBox.Yes:
            return
        
        success_count = 0
        fail_count = 0
        fail_names = []
        
        for name in names:
            success, msg = FileManager.permanent_delete(name)
            if success:
                success_count += 1
            else:
                fail_count += 1
                fail_names.append(f"{name}: {msg}")
        
        # 显示结果
        if fail_count == 0:
            QMessageBox.information(self, "成功", f"已永久删除 {success_count} 张图片")
        else:
            QMessageBox.warning(self, "部分失败",
                              f"成功删除 {success_count} 张，失败 {fail_count} 张\n\n" +
                              "\n".join(fail_names))
        
        self.load_data()
    
    def empty_trash(self):
        """清空垃圾桶"""
        if self.table.rowCount() == 0:
            QMessageBox.information(self, "提示", "垃圾桶已经是空的")
            return
        
        reply = QMessageBox.question(
            self, "确认清空",
            f"确定要清空整个垃圾桶吗？\n"
            f"这将永久删除 {self.table.rowCount()} 张图片，此操作不可撤销！",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        success, msg = FileManager.empty_trash()
        
        if success:
            QMessageBox.information(self, "成功", "垃圾桶已清空")
        else:
            QMessageBox.critical(self, "错误", f"清空失败: {msg}")
        
        self.load_data()
