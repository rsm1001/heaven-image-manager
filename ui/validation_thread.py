"""图片校验工作线程模块"""
from PyQt5.QtCore import QThread, pyqtSignal
from pathlib import Path
import logging

logger = logging.getLogger("HeavenComic")


class ValidationThread(QThread):
    """图片校验工作线程"""

    # 信号定义
    progress_signal = pyqtSignal(int, int, str)  # current, total, current_file
    completed_signal = pyqtSignal(list)  # results

    def __init__(self, validator, directory: Path):
        """初始化工作线程

        Args:
            validator: BatchValidator实例
            directory: 待校验目录路径
        """
        super().__init__()
        self.validator = validator
        self.directory = directory
        self.is_running = False

    def run(self):
        """执行校验任务"""
        logger.info(f"校验线程启动，目录: {self.directory}")
        self.is_running = True

        try:
            self.validator.validate_directory(
                self.directory,
                progress_callback=self._emit_progress,
                completed_callback=self._emit_completed
            )
        except Exception as e:
            logger.error(f"校验线程异常: {e}")

    def _emit_progress(self, current: int, total: int, current_file: str):
        """发射进度信号

        Args:
            current: 当前进度
            total: 总数
            current_file: 当前处理的文件名
        """
        self.progress_signal.emit(current, total, current_file)

    def _emit_completed(self, results: list):
        """发射完成信号

        Args:
            results: 校验结果列表
        """
        logger.info(f"校验完成，共 {len(results)} 个文件")
        self.completed_signal.emit(results)

    def stop(self):
        """停止校验任务"""
        logger.info("校验线程停止请求")
        self.is_running = False
        if self.validator:
            self.validator.cancel()
