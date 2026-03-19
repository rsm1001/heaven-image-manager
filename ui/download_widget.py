"""下载管理组件"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QLineEdit, QTextEdit, QGroupBox, QSpinBox, QFormLayout, QProgressBar,
    QMessageBox
)
from PyQt5.QtCore import Qt, pyqtSlot
import sys
from pathlib import Path
# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.downloader import ThumbnailDownloader
from utils.config import Config
from utils.logger import logger


class DownloadWidget(QWidget):
    """下载管理组件"""
    
    def __init__(self):
        super().__init__()
        self.downloader = ThumbnailDownloader()
        
        self.init_ui()
    
    def init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout(self)
        
        # 下载设置组
        settings_group = QGroupBox("下载设置")
        settings_layout = QFormLayout(settings_group)
        
        # 起始ID
        self.start_id_spin = QSpinBox()
        self.start_id_spin.setRange(1, 999999)
        self.start_id_spin.setValue(Config.START_ID)
        
        # 数量
        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 9999)
        self.count_spin.setValue(Config.TOTAL_COUNT)
        
        settings_layout.addRow("起始ID:", self.start_id_spin)
        settings_layout.addRow("下载数量:", self.count_spin)
        
        # 控制按钮组
        control_group = QGroupBox("下载控制")
        control_layout = QHBoxLayout(control_group)
        
        self.start_button = QPushButton("开始下载")
        self.start_button.clicked.connect(self.start_download)
        
        self.pause_button = QPushButton("暂停下载")
        self.pause_button.clicked.connect(self.pause_download)
        self.pause_button.setEnabled(False)
        
        self.stop_button = QPushButton("停止下载")
        self.stop_button.clicked.connect(self.stop_download)
        self.stop_button.setEnabled(False)
        
        control_layout.addWidget(self.start_button)
        control_layout.addWidget(self.pause_button)
        control_layout.addWidget(self.stop_button)
        control_layout.addStretch()
        
        # 进度显示组
        progress_group = QGroupBox("下载进度")
        progress_layout = QVBoxLayout(progress_group)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        
        # 进度标签
        self.progress_label = QLabel("准备就绪")
        
        progress_layout.addWidget(self.progress_label)
        progress_layout.addWidget(self.progress_bar)
        
        # 状态显示
        status_group = QGroupBox("下载状态")
        status_layout = QVBoxLayout(status_group)
        
        self.status_text = QTextEdit()
        self.status_text.setMaximumHeight(200)
        self.status_text.setReadOnly(True)
        
        status_layout.addWidget(self.status_text)
        
        # 添加到主布局
        layout.addWidget(settings_group)
        layout.addWidget(control_group)
        layout.addWidget(progress_group)
        layout.addWidget(status_group)
        layout.addStretch()
        
        logger.info("DownloadWidget initialized")
    
    def start_download(self):
        """开始下载"""
        start_id = self.start_id_spin.value()
        count = self.count_spin.value()
        
        # 验证输入
        if count <= 0:
            QMessageBox.warning(self, "警告", "下载数量必须大于0")
            return
        
        self.status_text.clear()
        self.log_status(f"准备开始下载：从ID {start_id}开始，共{count}张")
        
        # 启用/禁用按钮
        self.start_button.setEnabled(False)
        self.pause_button.setEnabled(True)
        self.stop_button.setEnabled(True)
        
        # 开始下载
        success = self.downloader.start_download(
            start_id=start_id,
            count=count,
            progress_callback=self.on_progress_update,
            completed_callback=self.on_download_completed,
            status_callback=self.on_status_update
        )
        
        if not success:
            QMessageBox.warning(self, "警告", "下载已在进行中")
            self.reset_buttons()
    
    @pyqtSlot(int, str)
    def on_progress_update(self, current, status):
        """进度更新回调"""
        percentage = int((current / self.count_spin.value()) * 100)
        self.progress_bar.setValue(percentage)
        self.progress_label.setText(f"进度: {current}/{self.count_spin.value()} ({percentage}%)")
    
    @pyqtSlot(dict)
    def on_download_completed(self, result):
        """下载完成回调"""
        self.log_status("=" * 50)
        if result.get("success"):
            success_count = result.get("success_count", 0)
            fail_count = result.get("fail_count", 0)
            total = result.get("total", 0)
            
            self.log_status(f"下载完成！总计{total}张，成功{success_count}张，失败{fail_count}张")
            
            fail_ids = result.get("fail_ids", [])
            if fail_ids:
                self.log_status(f"失败ID: {fail_ids}")
        else:
            if result.get("cancelled"):
                self.log_status("下载被用户取消")
            else:
                self.log_status("下载过程中出现错误")
        
        self.reset_buttons()
    
    @pyqtSlot(str)
    def on_status_update(self, status):
        """状态更新回调"""
        self.log_status(status)
    
    def pause_download(self):
        """暂停下载"""
        # 对于简单实现，我们只允许停止而不是暂停
        self.log_status("暂停功能暂未实现，点击停止按钮取消下载")
    
    def stop_download(self):
        """停止下载"""
        self.downloader.cancel_download()
        self.log_status("正在取消下载...")
        self.reset_buttons()
    
    def reset_buttons(self):
        """重置按钮状态"""
        self.start_button.setEnabled(True)
        self.pause_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_label.setText("准备就绪")
    
    def log_status(self, message):
        """记录状态消息"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.status_text.append(f"[{timestamp}] {message}")
    
    def refresh(self):
        """刷新界面"""
        self.log_status("界面已刷新")
        logger.info("DownloadWidget refreshed")
    
    def stop_all_downloads(self):
        """停止所有下载"""
        self.downloader.cancel_download()
        self.reset_buttons()