"""主窗口界面"""
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QLabel, QPushButton, QSplitter, QStatusBar, QMenuBar, QMenu,
    QAction, QFileDialog, QMessageBox, QGroupBox, QScrollArea, QSizePolicy,
    QDialog, QListWidget, QTextEdit, QSplitter
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QFont
import os
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


class LogViewerDialog(QDialog):
    """日志查看对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("查看日志")
        self.resize(800, 500)

        # 主布局
        layout = QHBoxLayout(self)

        # 左侧：日志文件列表
        self.log_list = QListWidget()
        self.log_list.setMaximumWidth(200)

        # 右侧：日志内容（只读）
        self.log_content = QTextEdit()
        self.log_content.setReadOnly(True)

        # 将列表和文本框放入分割器
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.log_list)
        splitter.addWidget(self.log_content)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

        layout.addWidget(splitter)

        # 扫描日志目录
        self.log_dir = project_root / "logs"
        self.load_log_list()

        # 连接信号
        self.log_list.currentRowChanged.connect(self.on_log_selected)

    def load_log_list(self):
        """加载日志文件列表"""
        if self.log_dir.exists():
            log_files = sorted(self.log_dir.glob("*.log"), reverse=True)
            for log_file in log_files:
                self.log_list.addItem(log_file.name)

    def on_log_selected(self, row):
        """选中日志文件时加载内容"""
        if row >= 0:
            log_name = self.log_list.item(row).text()
            log_path = self.log_dir / log_name
            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    self.log_content.setPlainText(f.read())
            except Exception as e:
                self.log_content.setPlainText(f"读取失败: {e}")


class MainWindow(QMainWindow):
    """主窗口类"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(Config.WINDOW_TITLE)
        self.setGeometry(100, 100, Config.WINDOW_WIDTH, Config.WINDOW_HEIGHT)

        # 设置窗口居中显示
        #if hasattr(Config, 'CENTER_ON_SCREEN') and Config.CENTER_ON_SCREEN:
        #    self.center_on_screen()

        # 初始化核心组件
        self.file_manager = FileManager()
        self.image_processor = ImageProcessor()

        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 主布局
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # 快捷按钮(垂直排列)
        button_column = QWidget()
        button_column_layout = QVBoxLayout(button_column)
        button_column_layout.setContentsMargins(0, 0, 0, 0)
        button_column_layout.setSpacing(2)

        self.open_101_button = QPushButton("📂 101")
        self.open_101_button.setFixedSize(80, 24)
        self.open_101_button.setStyleSheet("padding: 0; margin: 0;")
        font = self.open_101_button.font()
        font.setPointSize(8)
        self.open_101_button.setFont(font)
        self.open_101_button.clicked.connect(self.open_101_folder)

        self.undo_button = QPushButton("↩ 撤销")
        self.undo_button.setFixedSize(80, 24)
        self.undo_button.setStyleSheet("padding: 0; margin: 0;")
        self.undo_button.setEnabled(False)
        self.undo_button.clicked.connect(self.on_undo)

        button_column_layout.addWidget(self.open_101_button)
        button_column_layout.addWidget(self.undo_button)
        button_column_layout.addStretch()

        # 创建选项卡部件
        self.tab_widget = QTabWidget()
        self.tab_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.tab_widget.setStyleSheet("QTabWidget::pane { padding: 0; margin: 0; border: 0; }")

        # 创建各个功能部件
        self.preview_widget = PreviewWidget()
        self.manager_widget = ManagerWidget()
        self.download_widget = DownloadWidget()

        # 添加选项卡
        self.tab_widget.addTab(self.preview_widget, "图片预览")
        self.tab_widget.addTab(self.manager_widget, "图片管理")
        self.tab_widget.addTab(self.download_widget, "批量下载")

        # 将按钮组与选项卡放在同一行
        tab_row_layout = QHBoxLayout()
        tab_row_layout.setContentsMargins(0, 0, 0, 0)
        tab_row_layout.setSpacing(0)
        tab_row_layout.addWidget(button_column)
        tab_row_layout.addWidget(self.tab_widget, stretch=1)

        main_layout.addLayout(tab_row_layout)

        # 创建状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("就绪")

        # 创建菜单栏
        self.create_menu_bar()

        # 连接信号
        self.setup_connections()

        # 设置窗口居中显示
        if hasattr(Config, 'CENTER_ON_SCREEN') and Config.CENTER_ON_SCREEN:
            self.center_on_screen()

        logger.info("MainWindow initialized")

    def setup_connections(self):
        """设置信号连接"""
        # 当选项卡改变时更新状态
        self.tab_widget.currentChanged.connect(self.on_tab_changed)

    def center_on_screen(self):
        """将窗口居中显示在屏幕上"""
        # 获取主屏幕几何信息
        from PyQt5.QtWidgets import QDesktopWidget
        screen_geometry = QDesktopWidget().availableGeometry()

        # 计算窗口左上角坐标,使其居中
        x = (screen_geometry.width() - self.width()) // 2
        y = (screen_geometry.height() - self.height()) // 2

        # 移动窗口到计算出的位置
        self.move(x, y)

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

        # 查看菜单
        view_menu = menu_bar.addMenu('查看')

        log_action = QAction('查看日志', self)
        log_action.triggered.connect(self.show_log_viewer)
        view_menu.addAction(log_action)

        # 工具菜单
        tools_menu = menu_bar.addMenu('工具')

        refresh_action = QAction('刷新', self)
        refresh_action.triggered.connect(self.refresh_all)
        tools_menu.addAction(refresh_action)

        # 添加二次确认选项
        self.confirm_action = QAction('二次确认', self, checkable=True)
        self.confirm_action.setChecked(False)  # 默认关闭(不勾选)
        self.confirm_action.triggered.connect(self.toggle_confirmation)
        tools_menu.addAction(self.confirm_action)

        # 帮助菜单
        help_menu = menu_bar.addMenu('帮助')

        about_action = QAction('关于', self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def toggle_confirmation(self):
        """切换二次确认功能"""
        # 这里我们可以保存设置状态
        current_state = self.confirm_action.isChecked()
        self.status_bar.showMessage(f"二次确认: {'已开启' if current_state else '已关闭'}")

    def get_confirmation_setting(self):
        """获取二次确认设置状态"""
        return self.confirm_action.isChecked()

    def open_directory(self):
        """打开目录"""
        directory = QFileDialog.getExistingDirectory(
            self, "选择图片目录", str(Config.COMIC_DIR)
        )
        if directory:
            dir_path = Config.BASE_DIR / directory
            self.status_bar.showMessage(f"已选择目录: {dir_path}")
            logger.info(f"Selected directory: {dir_path}")

    def show_log_viewer(self):
        """显示日志查看器"""
        dialog = LogViewerDialog(self)
        dialog.exec_()

    def refresh_all(self):
        """刷新所有视图"""
        current_tab = self.tab_widget.currentIndex()

        if current_tab == 0:  # 图片预览
            self.preview_widget.refresh(reload=True)
        elif current_tab == 1:  # 图片管理
            self.manager_widget.refresh()
        elif current_tab == 2:  # 批量下载
            self.download_widget.refresh()

        self.status_bar.showMessage("已刷新")
        self.update_undo_button_state()

    def update_undo_button_state(self):
        """更新撤销按钮状态"""
        has_history = len(self.file_manager.undo_stack) > 0
        self.undo_button.setEnabled(has_history)

    def on_undo(self):
        """执行撤销操作"""
        success, msg, undone_record = self.file_manager.undo()
        if success:
            self.status_bar.showMessage(msg)
            last_op = undone_record

            if last_op and last_op.get("type") in ("move", "delete"):
                self.preview_widget.image_files = FileManager.get_image_files()

                # 对于 move 操作使用 source，对于 delete 操作使用 original_path
                op_data = last_op.get("data", {})
                restored_source = op_data.get("source") or op_data.get("original_path")

                # 定位到被撤回的文件
                found = False
                if restored_source:
                    for i, f in enumerate(self.preview_widget.image_files):
                        if str(f) == restored_source:
                            self.preview_widget.current_index = i
                            found = True
                            break

                if not found:
                    self.preview_widget.current_index = 0

                self.preview_widget.show_current_image()
                self.update_undo_button_state()
            elif last_op and last_op.get("type") in ("extract", "delete_item"):
                self.manager_widget.refresh()
                self.update_undo_button_state()
            else:
                self.refresh_all()
        else:
            QMessageBox.warning(self, "撤销失败", msg)

    def open_101_folder(self):
        """用系统文件管理器打开101文件夹"""
        folder_path = Config.TARGET_DIR
        if not folder_path.exists():
            folder_path.mkdir(parents=True, exist_ok=True)
        os.startfile(str(folder_path))
        self.status_bar.showMessage(f"已打开: {folder_path}")

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
            "功能:\n"
            "- 图片预览与分类\n"
            "- 批量图片名称提取\n"
            "- 批量图片下载\n\n"
            "基于PyQt5开发"
        )

    def closeEvent(self, event):
        """关闭事件处理"""
        # 停止所有后台任务
        self.download_widget.stop_all_downloads()

        # 获取二次确认设置
        confirmation_needed = self.get_confirmation_setting()

        if confirmation_needed:
            reply = QMessageBox.question(
                self, '确认退出',
                '确定要退出天堂图片管理器吗?',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                logger.info("Application closed by user")
                event.accept()
            else:
                event.ignore()
        else:
            # 如果关闭了二次确认,则直接关闭
            logger.info("Application closed by user")
            event.accept()