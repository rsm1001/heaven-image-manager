"""图片校验选项卡模块"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QGroupBox, QLineEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QProgressBar, QLabel, QSpinBox,
    QMessageBox, QHeaderView
)
from PyQt5.QtCore import Qt
from pathlib import Path
import sys
import logging
from datetime import datetime

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
from utils.config import Config
from core.image_validator import BatchValidator, ValidationReportExporter
from ui.validation_thread import ValidationThread

logger = logging.getLogger("HeavenComic")


class ValidatorTabWidget(QWidget):
    """图片校验选项卡组件"""

    def __init__(self, parent_widget):
        """初始化选项卡

        Args:
            parent_widget: 父组件引用（ManagerWidget）
        """
        super().__init__()
        self.parent_widget = parent_widget
        self.validator = None
        self.validation_thread = None
        self._create_ui()

    def _create_ui(self):
        """创建UI"""
        layout = QVBoxLayout(self)

        # 校验设置组
        settings_group = QGroupBox("校验设置")
        settings_layout = QFormLayout(settings_group)

        # 目录选择
        dir_layout = QHBoxLayout()
        self.validator_dir_input = QLineEdit()
        self.validator_dir_input.setText(str(Config.COMIC_DIR))
        browse_button = QPushButton("浏览...")
        browse_button.clicked.connect(self._on_browse_validator_dir)
        dir_layout.addWidget(self.validator_dir_input)
        dir_layout.addWidget(browse_button)
        settings_layout.addRow("校验目录:", dir_layout)

        # 校验线程数
        thread_layout = QHBoxLayout()
        self.validator_threads_spin = QSpinBox()
        self.validator_threads_spin.setRange(1, 16)
        self.validator_threads_spin.setValue(5)
        thread_layout.addWidget(self.validator_threads_spin)
        thread_layout.addWidget(QLabel("线程"))
        thread_layout.addStretch()
        settings_layout.addRow("并发线程:", thread_layout)

        # 控制按钮
        button_layout = QHBoxLayout()
        self.validator_start_button = QPushButton("开始校验")
        self.validator_start_button.clicked.connect(self._on_start_validation)
        self.validator_stop_button = QPushButton("停止校验")
        self.validator_stop_button.clicked.connect(self._on_stop_validation)
        self.validator_stop_button.setEnabled(False)
        button_layout.addWidget(self.validator_start_button)
        button_layout.addWidget(self.validator_stop_button)
        button_layout.addStretch()
        settings_layout.addRow("", button_layout)

        layout.addWidget(settings_group)

        # 进度显示组
        progress_group = QGroupBox("校验进度")
        progress_layout = QVBoxLayout(progress_group)
        self.validator_progress_bar = QProgressBar()
        self.validator_progress_label = QLabel("待校验")
        progress_layout.addWidget(self.validator_progress_label)
        progress_layout.addWidget(self.validator_progress_bar)
        layout.addWidget(progress_group)

        # 结果显示组
        result_group = QGroupBox("校验结果")
        result_layout = QVBoxLayout(result_group)

        self.validator_result_table = QTableWidget()
        self.validator_result_table.setColumnCount(4)
        self.validator_result_table.setHorizontalHeaderLabels(["状态", "文件名", "大小(KB)", "错误信息"])
        self.validator_result_table.setColumnWidth(0, 60)
        self.validator_result_table.setColumnWidth(1, 150)
        self.validator_result_table.setColumnWidth(2, 80)
        self.validator_result_table.horizontalHeader().setStretchLastSection(True)
        self.validator_result_table.setMinimumHeight(200)

        self.validator_summary_label = QLabel("待校验")
        result_layout.addWidget(self.validator_summary_label)
        result_layout.addWidget(self.validator_result_table)
        layout.addWidget(result_group)

        # 操作按钮组
        action_layout = QHBoxLayout()
        self.validator_export_json_button = QPushButton("导出JSON报告")
        self.validator_export_json_button.clicked.connect(self._on_export_validation_json)
        self.validator_export_json_button.setEnabled(False)

        self.validator_export_txt_button = QPushButton("导出TXT报告")
        self.validator_export_txt_button.clicked.connect(self._on_export_validation_txt)
        self.validator_export_txt_button.setEnabled(False)

        self.validator_delete_button = QPushButton("删除选中(不经过垃圾桶)")
        self.validator_delete_button.clicked.connect(self._on_delete_selected_corrupted)
        self.validator_delete_button.setEnabled(False)

        action_layout.addWidget(self.validator_export_json_button)
        action_layout.addWidget(self.validator_export_txt_button)
        action_layout.addWidget(self.validator_delete_button)
        action_layout.addStretch()
        layout.addLayout(action_layout)

    def _on_browse_validator_dir(self):
        """浏览校验目录"""
        from PyQt5.QtWidgets import QFileDialog

        initial_dir = Config.COMIC_DIR
        if not initial_dir.exists():
            initial_dir = Config.BASE_DIR

        dir_path = QFileDialog.getExistingDirectory(
            self, "选择要校验图片的目录", str(initial_dir)
        )

        if dir_path:
            self.validator_dir_input.setText(dir_path)

    def _on_start_validation(self):
        """开始校验"""
        dir_path = self.validator_dir_input.text().strip()
        if not dir_path:
            QMessageBox.warning(self, "警告", "请输入校验目录路径")
            return

        directory = Path(dir_path)
        if not directory.is_absolute():
            directory = Config.BASE_DIR / directory

        if not directory.exists():
            QMessageBox.warning(self, "警告", f"目录不存在: {directory}")
            return

        logger.info(f"开始校验目录: {directory}")

        # 更新按钮状态
        self.validator_start_button.setEnabled(False)
        self.validator_stop_button.setEnabled(True)
        self.validator_export_json_button.setEnabled(False)
        self.validator_export_txt_button.setEnabled(False)
        self.validator_delete_button.setEnabled(False)

        # 清空结果表格
        self.validator_result_table.setRowCount(0)

        # 创建校验器
        max_workers = self.validator_threads_spin.value()
        self.validator = BatchValidator(max_workers=max_workers)

        # 启动后台校验线程
        self.validation_thread = ValidationThread(self.validator, directory)
        self.validation_thread.progress_signal.connect(self._on_validation_progress)
        self.validation_thread.completed_signal.connect(self._on_validation_completed)
        self.validation_thread.start()

    def _on_stop_validation(self):
        """停止校验"""
        if self.validation_thread:
            self.validation_thread.stop()
            self.validation_thread.wait()
        if self.validator:
            self.validator.cancel()
        self._reset_validator_buttons()
        self.validator_progress_label.setText("校验已停止")
        logger.info("校验已停止")

    def _on_validation_progress(self, current: int, total: int, current_file: str):
        """校验进度回调"""
        percentage = int((current / total) * 100) if total > 0 else 0
        self.validator_progress_bar.setValue(percentage)
        self.validator_progress_label.setText(f"校验中: {current}/{total} ({percentage}%) - {current_file}")

    def _on_validation_completed(self, results: list):
        """校验完成回调"""
        self._reset_validator_buttons()

        corrupted = [r for r in results if not r.is_valid]
        valid = [r for r in results if r.is_valid]

        logger.info(f"校验完成，总计: {len(results)}，正常: {len(valid)}，损坏: {len(corrupted)}")

        self.validator_summary_label.setText(
            f"校验完成 - 总计: {len(results)} 张, 正常: {len(valid)} 张, 损坏: {len(corrupted)} 张"
        )

        # 填充结果表格
        self.validator_result_table.setRowCount(len(results))
        for row, result in enumerate(results):
            status_item = QTableWidgetItem("✓" if result.is_valid else "✗")
            status_item.setForeground(Qt.green if result.is_valid else Qt.red)
            self.validator_result_table.setItem(row, 0, status_item)
            self.validator_result_table.setItem(row, 1, QTableWidgetItem(result.path.name))
            self.validator_result_table.setItem(row, 2, QTableWidgetItem(str(result.file_size_kb)))
            error_text = "" if result.is_valid else (result.error_msg or result.error_type or "未知错误")
            self.validator_result_table.setItem(row, 3, QTableWidgetItem(error_text))

        # 启用导出按钮
        if corrupted:
            self.validator_export_json_button.setEnabled(True)
            self.validator_export_txt_button.setEnabled(True)
            self.validator_delete_button.setEnabled(True)

        self.validator_progress_label.setText(f"校验完成 - 发现 {len(corrupted)} 张损坏图片")

    def _reset_validator_buttons(self):
        """重置校验按钮状态"""
        self.validator_start_button.setEnabled(True)
        self.validator_stop_button.setEnabled(False)

    def _on_export_validation_json(self):
        """导出JSON报告"""
        if not self.validator:
            return

        results = self.validator._results
        if not results:
            QMessageBox.warning(self, "警告", "没有可导出的校验结果")
            return

        from PyQt5.QtWidgets import QFileDialog

        dir_path = self.validator_dir_input.text().strip()
        directory = Path(dir_path) if dir_path else Config.COMIC_DIR
        default_name = f"corrupted_images_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出JSON报告", str(directory / default_name),
            "JSON Files (*.json)"
        )

        if file_path:
            if ValidationReportExporter.export_json(results, Path(file_path)):
                logger.info(f"JSON报告已导出: {file_path}")
                QMessageBox.information(self, "成功", f"JSON报告已导出:\n{file_path}")
            else:
                logger.error("JSON报告导出失败")
                QMessageBox.critical(self, "错误", "导出JSON报告失败")

    def _on_export_validation_txt(self):
        """导出TXT报告"""
        if not self.validator:
            return

        results = self.validator._results
        if not results:
            QMessageBox.warning(self, "警告", "没有可导出的校验结果")
            return

        from PyQt5.QtWidgets import QFileDialog

        dir_path = self.validator_dir_input.text().strip()
        directory = Path(dir_path) if dir_path else Config.COMIC_DIR
        default_name = f"corrupted_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出TXT报告", str(directory / default_name),
            "Text Files (*.txt)"
        )

        if file_path:
            if ValidationReportExporter.export_txt(results, Path(file_path), directory):
                logger.info(f"TXT报告已导出: {file_path}")
                QMessageBox.information(self, "成功", f"TXT报告已导出:\n{file_path}")
            else:
                logger.error("TXT报告导出失败")
                QMessageBox.critical(self, "错误", "导出TXT报告失败")

    def _on_delete_selected_corrupted(self):
        """删除选中的损坏图片"""
        if not self.validator:
            return

        selected_rows = self.validator_result_table.selectedIndexes()
        if not selected_rows:
            QMessageBox.warning(self, "警告", "请先选择要删除的图片")
            return

        row_set = set()
        for index in selected_rows:
            row_set.add(index.row())

        corrupted = self.validator.get_corrupted()
        selected_corrupted = []
        for row in sorted(row_set):
            if row < len(corrupted):
                selected_corrupted.append(corrupted[row])

        if not selected_corrupted:
            QMessageBox.warning(self, "警告", "选中的图片中没有损坏的图片")
            return

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要永久删除选中的 {len(selected_corrupted)} 张损坏图片吗？\n此操作不可撤销！",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        deleted_count = 0
        for result in selected_corrupted:
            try:
                if result.path.exists():
                    result.path.unlink()
                    deleted_count += 1
                    logger.info(f"已删除损坏图片: {result.path}")
            except Exception as e:
                logger.error(f"删除图片失败 {result.path}: {e}")

        QMessageBox.information(self, "完成", f"已删除 {deleted_count} 张损坏图片")
        self._on_validation_completed(self.validator._results)


def create_validator_tab(parent_widget) -> QWidget:
    """创建图片校验选项卡（工厂函数）

    Args:
        parent_widget: 父组件引用

    Returns:
        QWidget: 创建的选项卡组件
    """
    return ValidatorTabWidget(parent_widget)
