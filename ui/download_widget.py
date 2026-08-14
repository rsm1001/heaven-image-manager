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

from core.download.downloader import ThumbnailDownloader
from utils.config import Config
from utils.logger import logger
from utils.notifier import notifier


class DownloadWidget(QWidget):
    """下载管理组件"""
    
    def __init__(self):
        super().__init__()
        self.downloader = ThumbnailDownloader()
        # 添加一个属性来跟踪当前下载的进度
        self.current_start_id = None
        self.current_count = None
        self.downloaded_count = 0  # 已下载的数量
        self.successful_downloads = set()  # 记录确切成功下载的ID集合
        
        self.init_ui()
    
    def init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout(self)
        
        # 下载设置组
        settings_group = QGroupBox("下载设置")
        settings_layout = QFormLayout(settings_group)
        
        # 起始ID - 从 Config 统一读取（内部封装了 config.json 读取和 fallback 逻辑）
        self.start_id_spin = QSpinBox()
        self.start_id_spin.setRange(1, 999999)
        last_downloaded = Config.get_last_downloaded_id()
        self.start_id_spin.setValue(last_downloaded + 1)  # 使用最后下载ID的下一个作为默认值
        
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
        
        self.stop_button = QPushButton("停止下载")
        self.stop_button.clicked.connect(self.stop_download)
        self.stop_button.setEnabled(False)
        
        control_layout.addWidget(self.start_button)
        control_layout.addWidget(self.stop_button)
        # 移除暂停按钮
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
        
        # 记录当前下载参数
        self.current_start_id = start_id
        self.current_count = count
        self.downloaded_count = 0  # 重置已下载计数
        self.successful_downloads.clear()  # 清空成功下载记录
        
        # 启用/禁用按钮
        self.start_button.setEnabled(False)
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
        
        # 更新已下载数量
        self.downloaded_count = current

        # 注意：此时我们不更新成功的下载记录，因为进度只表示尝试下载的数量，
        # 实际的成功与否需要通过下载结果来确认
        # 这里只是UI更新，不处理成功ID的记录
    
    @pyqtSlot(dict)
    def on_download_completed(self, result):
        """Use the worker's persisted checkpoint to refresh the UI."""
        self.log_status("=" * 50)
        success_count = result.get("success_count", 0)
        fail_count = result.get("fail_count", 0)
        total = result.get("total", 0)

        if result.get("cancelled"):
            self.log_status("下载被用户取消")
        elif result.get("success"):
            self.log_status(
                f"下载完成！总计{total}张，"
                f"成功{success_count}张，失败{fail_count}张"
            )
        else:
            self.log_status("下载过程中出现错误")

        fail_ids = result.get("fail_ids", [])
        if fail_ids:
            self.log_status(
                f"失败ID: {fail_ids}"
                "（续传点已越过失败项，可手动改回起始ID重试）"
            )

        if result.get("checkpoint_saved"):
            next_start_id = result.get("next_start_id")
            resume_id = result.get("resume_id")
            # 微调框跟随本次请求的续传点，不改写用户手动选择的范围；
            # 全局续传点只作提示，避免把起始ID悄悄拖回检查点缺口。
            if resume_id is not None:
                self.start_id_spin.setValue(resume_id)
                if next_start_id is not None and next_start_id != resume_id:
                    self.log_status(
                        f"下次下载将从ID {resume_id} 继续；"
                        f"全局续传点为 {next_start_id}"
                    )
                else:
                    self.log_status(
                        f"下次下载将从ID {resume_id} 开始"
                    )
            elif next_start_id is not None:
                self.start_id_spin.setValue(next_start_id)
                self.log_status(
                    f"下次下载将从ID {next_start_id} 开始"
                )
        else:
            self.log_status(
                "下载检查点保存失败，"
                "请勿关闭程序并检查配置文件写入权限"
            )
            logger.error("Download checkpoint was not persisted")

        if result.get("records_saved") is False:
            self.log_status(
                "下载记录保存失败，"
                "但图片文件已保留"
            )
            logger.error("Download records were not persisted")

        self.reset_buttons()

        # Notify through win10toast, QSystemTrayIcon, or logging fallback.
        partial_cleaned = result.get("partial_files_cleaned", 0)
        if success_count > 0:
            notifier.notify(
                "下载完成",
                f"成功 {success_count} 张，"
                f"失败 {fail_count} 张",
                duration=5,
            )
        if partial_cleaned:
            self.log_status(
                f"已清理 {partial_cleaned} "
                "个上次未完成的临时文件"
            )

    @pyqtSlot(str)
    def on_status_update(self, status):
        """状态更新回调"""
        self.log_status(status)
    
    def _download_running(self) -> bool:
        """当前是否有下载 worker 在运行（或已 start() 但尚未进入 run()）。"""
        worker = self.downloader.worker
        return bool(worker and (worker.isRunning() or worker.is_running))

    def stop_download(self):
        """Stop downloading and wait for the worker completion callback before re-enabling controls."""
        # 先置取消标志：即使 worker 刚 start() 还没进入 run()，取消也不能丢
        self.downloader.cancel_download()
        if not self._download_running():
            # 线程已结束（或从未启动），completed_signal 不会来，直接复位。
            self.reset_buttons()
            return
        self.log_status("Cancelling download...")
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(False)
    
    def reset_buttons(self):
        """重置按钮状态"""
        self.start_button.setEnabled(True)
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
        """Stop all downloads and let the completion callback restore the UI."""
        self.downloader.cancel_download()
        if not self._download_running():
            # 没有下载在跑：不要禁用按钮，否则没有信号来恢复它们。
            return
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(False)

    def shutdown_downloads(self):
        """应用退出前调用：取消并阻塞等待下载线程退出。

        与 stop_all_downloads 不同，这里必须 join——窗口销毁后 QThread
        若仍在运行会直接 abort 进程，可能打断记录/检查点写入。
        """
        self.downloader.shutdown()
    
    def pause_download(self):
        """暂停下载 - 已移除此功能"""
        # 暂停功能已移除，此方法保留以防其他地方调用
        pass
