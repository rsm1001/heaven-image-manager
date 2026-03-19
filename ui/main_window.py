"""主窗口界面"""
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QLabel, QPushButton, QSplitter, QStatusBar, QMenuBar, QMenu,
    QAction, QFileDialog, QMessageBox, QGroupBox, QScrollArea
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QFont
import sys
from pathlib import Path
# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.file_manager import FileManager
from core.image_processor import ImageProcessor
from utils.config import Config
from utils.logger import logger
from .preview_widget import PreviewWidget
from .manager_widget import ManagerWidget
from .download_widget import DownloadWidget


class MainWindow(QMainWindow):
    """主窗口类"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle(Config.WINDOW_TITLE)
        self.setGeometry(100, 100, Config.WINDOW_WIDTH, Config.WINDOW_HEIGHT)
        
        # 初始化核心组件
        self.file_manager = FileManager()
        self.image_processor = ImageProcessor()
        
        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QVBoxLayout(central_widget)
        
        # 创建选项卡部件
        self.tab_widget = QTabWidget()
        
        # 创建各个功能部件
        self.preview_widget = PreviewWidget()
        self.manager_widget = ManagerWidget()
        self.download_widget = DownloadWidget()
        
        # 添加选项卡
        self.tab_widget.addTab(self.preview_widget, "图片预览")
        self.tab_widget.addTab(self.manager_widget, "图片管理")
        self.tab_widget.addTab(self.download_widget, "批量下载")
        
        main_layout.addWidget(self.tab_widget)
        
        # 创建状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪")
        
        # 创建菜单栏
        self.create_menu_bar()
        
        # 连接信号
        self.setup_connections()
        
        logger.info("MainWindow initialized")
    
    def create_menu_bar(self):
        """创建菜单栏"""
        menu_bar = self.menuBar()
        
        # 文件菜单
        file_menu = menu_bar.addMenu('文件')
        
        open_action = QAction('打开目录', self)
        open_action.triggered.connect(self.open_directory)
        file_menu.addAction(open_action)
        
        exit_action = QAction('退出', self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # 工具菜单
        tools_menu = menu_bar.addMenu('工具')
        
        refresh_action = QAction('刷新', self)
        refresh_action.triggered.connect(self.refresh_all)
        tools_menu.addAction(refresh_action)
        
        # 帮助菜单
        help_menu = menu_bar.addMenu('帮助')
        
        about_action = QAction('关于', self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    
    def setup_connections(self):
        """设置信号连接"""
        # 当选项卡改变时更新状态
        self.tab_widget.currentChanged.connect(self.on_tab_changed)
    
    def open_directory(self):
        """打开目录"""
        directory = QFileDialog.getExistingDirectory(
            self, "选择图片目录", str(Config.COMIC_DIR)
        )
        if directory:
            dir_path = Config.BASE_DIR / directory
            self.status_bar.showMessage(f"已选择目录: {dir_path}")
            logger.info(f"Selected directory: {dir_path}")
    
    def refresh_all(self):
        """刷新所有视图"""
        current_tab = self.tab_widget.currentIndex()
        
        if current_tab == 0:  # 图片预览
            self.preview_widget.refresh()
        elif current_tab == 1:  # 图片管理
            self.manager_widget.refresh()
        elif current_tab == 2:  # 批量下载
            self.download_widget.refresh()
        
        self.status_bar.showMessage("已刷新")
    
    def on_tab_changed(self, index):
        """选项卡改变时的处理"""
        tab_names = ["图片预览", "图片管理", "批量下载"]
        if 0 <= index < len(tab_names):
            self.status_bar.showMessage(f"当前: {tab_names[index]}")
    
    def show_about(self):
        """显示关于对话框"""
        QMessageBox.about(
            self,
            "关于天堂图片管理器",
            "天堂图片管理器 - PyQt版本\n\n"
            "功能：\n"
            "- 图片预览与分类\n"
            "- 批量图片名称提取\n"
            "- 批量图片下载\n\n"
            "基于PyQt5开发"
        )
    
    def closeEvent(self, event):
        """关闭事件处理"""
        # 停止所有后台任务
        self.download_widget.stop_all_downloads()
        
        reply = QMessageBox.question(
            self, '确认退出',
            '确定要退出天堂图片管理器吗？',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            logger.info("Application closed by user")
            event.accept()
        else:
            event.ignore()