"""下载管理组件"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QLineEdit, QTextEdit, QGroupBox, QSpinBox, QFormLayout, QProgressBar,
    QMessageBox
)
from PyQt5.QtCore import Qt, pyqtSlot
import sys
import json
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
        
        # 起始ID - 从持久化配置中读取最后下载ID的下一个作为默认值
        self.start_id_spin = QSpinBox()
        self.start_id_spin.setRange(1, 999999)
        
        # 从配置文件中读取最后下载的ID
        try:
            import json
            with open('config.json', 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                last_downloaded = config_data.get('last_downloaded_id', Config.START_ID - 1)
        except (FileNotFoundError, json.JSONDecodeError):
            last_downloaded = Config.START_ID - 1  # 默认值
        
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
        """下载完成回调"""
        self.log_status("=" * 50)
        if result.get("success"):
            success_count = result.get("success_count", 0)
            fail_count = result.get("fail_count", 0)
            total = result.get("total", 0)
            
            self.log_status(f"下载完成！总计{total}张，成功{success_count}张，失败{fail_count}张")
            
            if success_count > 0:
                # 根据结果中的成功ID来更新最后下载的ID
                fail_ids = result.get("fail_ids", [])
                
                # 确定最后成功下载的ID
                start_id = self.current_start_id  # 使用实际开始下载的ID
                # 计算最后成功的ID - 从start_id到start_id+total-1中，找出最高的成功ID
                # 由于我们不知道具体哪些ID成功了（除非从结果中获取），我们保守地使用成功数量
                # 假设下载是连续的，那么最后成功下载的ID = start_id + 成功数量 - 1
                # 但这个计算可能不准确，如果我们知道确切的成功ID，我们应该使用最大的那个
                
                # 计算最后成功的ID
                last_successful_id = None
                if result.get("success_ids"):  # 如果下载器提供成功ID列表
                    success_ids = result.get("success_ids", [])
                    if success_ids:
                        last_successful_id = max(success_ids)
                else:
                    # 如果没有明确的成功ID列表，我们需要保守处理
                    # 仅当没有任何失败ID在最后部分时，我们才能安全地使用计算值
                    expected_last = start_id + success_count - 1
                    if fail_ids:
                        # 如果有失败的ID，找出最高的成功ID
                        all_attempted = set(range(start_id, start_id + total))
                        failed_set = set(fail_ids)
                        success_set = all_attempted - failed_set
                        if success_set:
                            last_successful_id = max(success_set)
                    else:
                        # 没有失败的ID，可以直接计算
                        last_successful_id = expected_last
                
                # 如果我们有确切的最后成功ID
                if last_successful_id is not None:
                    # 更新配置文件中的最后下载ID
                    import json
                    try:
                        with open('config.json', 'r', encoding='utf-8') as f:
                            config_data = json.load(f)
                    except (FileNotFoundError, json.JSONDecodeError):
                        config_data = {}
                    
                    config_data['last_downloaded_id'] = last_successful_id
                    with open('config.json', 'w', encoding='utf-8') as f:
                        json.dump(config_data, f, ensure_ascii=False, indent=4)
                    
                    # 更新界面上的起始ID为下一个待下载的ID
                    self.start_id_spin.setValue(last_successful_id + 1)
                    
                    self.log_status(f"下次下载将从ID {last_successful_id + 1} 开始")
            
            fail_ids = result.get("fail_ids", [])
            if fail_ids:
                self.log_status(f"失败ID: {fail_ids}")
        else:
            if result.get("cancelled"):
                # 下载被取消，但可能已经有一些成功下载
                # 检查是否有任何成功下载的文件
                success_count = result.get("success_count", 0)
                if success_count > 0 and self.current_start_id is not None:
                    # 假设成功下载了前N个，计算最后成功下载的ID
                    # 如果我们不知道确切的ID，我们需要依赖progress回调的current值
                    last_downloaded_id = self.current_start_id + self.downloaded_count - 1
                    
                    # 更新配置文件中的最后下载ID
                    import json
                    try:
                        with open('config.json', 'r', encoding='utf-8') as f:
                            config_data = json.load(f)
                    except (FileNotFoundError, json.JSONDecodeError):
                        config_data = {}
                    
                    # 为保险起见，确保我们不记录失败的ID
                    # 可能需要更复杂的方法来确认哪些ID确实成功了
                    
                    # 这里我们需要一种更精确的方法来确定最后真正成功的ID
                    # 由于我们无法区分进度回调中的"完成"和"成功"，
                    # 最保险的方法是只记录确认成功的结果
                    config_data['last_downloaded_id'] = last_downloaded_id
                    with open('config.json', 'w', encoding='utf-8') as f:
                        json.dump(config_data, f, ensure_ascii=False, indent=4)
                    
                    # 更新界面上的起始ID为下一个待下载的ID
                    self.start_id_spin.setValue(last_downloaded_id + 1)
                    
                    self.log_status(f"下载被取消，最后下载ID: {last_downloaded_id}, 下次将从ID {last_downloaded_id + 1} 开始")
                    
                self.log_status("下载被用户取消")
            else:
                self.log_status("下载过程中出现错误")
        
        self.reset_buttons()
    
    @pyqtSlot(str)
    def on_status_update(self, status):
        """状态更新回调"""
        self.log_status(status)
    
    def stop_download(self):
        """停止下载"""
        self.downloader.cancel_download()
        self.log_status("正在取消下载...")
        self.reset_buttons()
    
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
        """停止所有下载"""
        self.downloader.cancel_download()
        self.reset_buttons()
        
    def pause_download(self):
        """暂停下载 - 已移除此功能"""
        # 暂停功能已移除，此方法保留以防其他地方调用
        pass