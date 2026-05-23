"""图片管理组件模块（协调层）

职责：
- 管理各选项卡的生命周期
- 提供跨选项卡的状态同步
- 处理刷新等协调性操作
"""
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QTabWidget
from pathlib import Path
import logging
import sys

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.logger import logger
from ui.tabs.extract_tab import create_extract_tab
from ui.tabs.data_tab import create_data_tab
from ui.tabs.stats_tab import create_stats_tab
from ui.tabs.validator_tab import create_validator_tab

logger = logging.getLogger("HeavenComic")


class ManagerWidget(QWidget):
    """图片管理组件（协调层）

    协调各选项卡组件，管理共享状态
    """

    def __init__(self):
        super().__init__()
        self._init_ui()
        logger.info("ManagerWidget 初始化完成")

    def _init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout(self)

        # 创建选项卡
        tab_widget = QTabWidget()

        # 添加各选项卡
        tab_widget.addTab(create_extract_tab(self), "文件提取")
        tab_widget.addTab(create_data_tab(self), "数据管理")
        tab_widget.addTab(create_stats_tab(self), "统计信息")
        tab_widget.addTab(create_validator_tab(self), "图片校验")

        layout.addWidget(tab_widget)

    def update_stats(self):
        """更新统计信息（供外部调用）"""
        logger.debug("更新统计信息")

    def refresh(self):
        """刷新所有数据（供外部调用）"""
        logger.info("刷新所有数据")
