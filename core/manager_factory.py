"""管理器工厂模块 - 统一创建和管理各模块实例"""
from typing import Optional
from utils.logger import logger


class ManagerFactory:
    """管理器工厂类"""

    _instances = {}

    @classmethod
    def get_manager(cls, manager_type: str):
        """获取管理器实例（单例模式）

        Args:
            manager_type: 管理器类型名称

        Returns:
            管理器实例
        """
        if manager_type not in cls._instances:
            cls._instances[manager_type] = cls._create_manager(manager_type)
        return cls._instances[manager_type]

    @classmethod
    def _create_manager(cls, manager_type: str):
        """创建管理器实例

        Args:
            manager_type: 管理器类型名称

        Returns:
            管理器实例
        """
        if manager_type == "file":
            from core.file_manager import FileManager
            return FileManager
        elif manager_type == "undo":
            from core.undo_manager import UndoManager
            return UndoManager
        elif manager_type == "trash":
            from core.trash_manager import TrashManager
            return TrashManager
        elif manager_type == "json":
            from core.json_storage import JsonStorage
            return JsonStorage
        else:
            raise ValueError(f"未知的管理器类型: {manager_type}")

    @classmethod
    def reset(cls):
        """重置所有管理器实例（主要用于测试）"""
        cls._instances.clear()
        logger.debug("管理器实例已重置")
