#!/usr/bin/env python3
"""天堂图片管理器 - PyQt版本主入口"""

import sys
import os
from pathlib import Path

# 设置Qt属性 - 必须在创建QApplication之前设置
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

# 启用高DPI缩放
if hasattr(Qt, 'AA_EnableHighDpiScaling'):
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from PyQt5.QtGui import QFont
from ui.main_window import MainWindow
from utils.logger import logger


def main():
    """主函数"""
    try:
        # 创建Qt应用
        app = QApplication(sys.argv)
        
        # 设置应用属性
        app.setApplicationName("天堂图片管理器")
        app.setApplicationVersion("1.0.0")
        app.setOrganizationName("HeavenComic")
        
        # 设置默认字体
        font = QFont("Microsoft YaHei", 9)
        app.setFont(font)
        
        # 创建并显示主窗口
        window = MainWindow()
        window.show()
        
        # 记录启动信息
        logger.info("Application started successfully")
        
        # 运行应用
        exit_code = app.exec_()
        
        # 记录退出信息
        logger.info(f"Application exited with code: {exit_code}")
        
        sys.exit(exit_code)
        
    except Exception as e:
        logger.error(f"Application error: {str(e)}", exc_info=True)
        print(f"启动应用时发生错误: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()