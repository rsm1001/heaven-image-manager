"""Undo/Redo操作历史管理模块"""
from typing import List, Tuple, Optional, Dict, Any
from pathlib import Path
import shutil

from utils.logger import logger
from utils.config import Config


class UndoOperationType:
    """Undo操作类型常量"""
    MOVE = "move"
    DELETE = "delete"
    EXTRACT = "extract"
    DELETE_ITEM = "delete_item"


class UndoManager:
    """Undo/Redo操作历史管理类"""

    # 操作历史栈（会话级，不持久化）
    _undo_stack: List[Dict[str, Any]] = []

    @classmethod
    def push(cls, record: dict) -> None:
        """记录操作到历史栈

        Args:
            record: 操作记录，包含 type 和 data
        """
        cls._undo_stack.append(record)
        logger.info(f"操作已记录: {record['type']}")

    @classmethod
    def pop(cls) -> Optional[Dict[str, Any]]:
        """弹出最近的操作记录"""
        if cls._undo_stack:
            return cls._undo_stack.pop()
        return None

    @classmethod
    def undo(cls) -> Tuple[bool, str, Optional[dict]]:
        """执行撤销操作（逆序）

        Returns:
            Tuple[bool, str, Optional[dict]]: (是否成功, 消息, 被撤销的记录)
        """
        if not cls._undo_stack:
            return False, "没有可撤销的操作", None

        record = cls.pop()
        op_type = record.get("type")
        data = record.get("data", {})

        try:
            if op_type == UndoOperationType.MOVE:
                result = cls._undo_move(data)
                return result[0], result[1], record
            elif op_type == UndoOperationType.DELETE:
                result = cls._undo_delete(data)
                return result[0], result[1], record
            elif op_type == UndoOperationType.EXTRACT:
                result = cls._undo_extract(data)
                return result[0], result[1], record
            elif op_type == UndoOperationType.DELETE_ITEM:
                result = cls._undo_delete_item(data)
                return result[0], result[1], record
            else:
                logger.error(f"未知的操作类型: {op_type}")
                return False, f"未知的操作类型: {op_type}", record
        except Exception as e:
            logger.error(f"撤销操作失败: {e}")
            return False, f"撤销失败: {e}", None

    @classmethod
    def clear(cls) -> None:
        """清空操作历史"""
        cls._undo_stack.clear()
        logger.info("操作历史已清空")

    @classmethod
    def is_empty(cls) -> bool:
        """检查是否有可撤销的操作"""
        return len(cls._undo_stack) == 0

    @classmethod
    def size(cls) -> int:
        """获取历史栈大小"""
        return len(cls._undo_stack)

    @classmethod
    def _undo_move(cls, data: dict) -> Tuple[bool, str]:
        """撤销移动操作"""
        source = data.get("source")
        target = data.get("target")

        if not source or not target:
            return False, "移动记录数据不完整"

        source_path = Path(source) if isinstance(source, str) else source
        target_path = Path(target) if isinstance(target, str) else target

        if not target_path.exists():
            return False, f"文件已被移动或删除: {target_path.name}"

        if source_path.exists():
            counter = 1
            while source_path.exists():
                source_path = target_path.parent / f"{source_path.stem}_{counter}{target_path.suffix}"
                counter += 1

        shutil.move(str(target_path), str(source_path))
        logger.info(f"撤销移动: {target_path} -> {source_path}")
        return True, f"已撤销移动: {source_path.name}"

    @classmethod
    def _undo_delete(cls, data: dict) -> Tuple[bool, str]:
        """撤销删除操作"""
        name = data.get("name")

        if not name:
            return False, "删除记录数据不完整"

        # 延迟导入避免循环引用
        from core.trash_manager import TrashManager
        success, msg = TrashManager.restore(name)
        return success, f"已撤销删除: {name}" if success else msg

    @classmethod
    def _undo_extract(cls, data: dict) -> Tuple[bool, str]:
        """撤销提取操作"""
        from core.json_storage import JsonStorage

        added_items = data.get("added_items", [])
        json_path = data.get("json_path")

        if not added_items:
            return False, "没有可撤销的提取项"

        if json_path is None:
            json_path = Config.COMIC_DIR / "image_names.json"
        else:
            json_path = Path(json_path) if isinstance(json_path, str) else json_path

        added_names = {item.get("name") for item in added_items}
        JsonStorage.remove_items_by_names(json_path, added_names)
        logger.info(f"撤销提取: 移除了 {len(added_items)} 项")
        return True, f"已撤销提取: 移除了 {len(added_items)} 项"

    @classmethod
    def _undo_delete_item(cls, data: dict) -> Tuple[bool, str]:
        """撤销删除JSON项操作"""
        from core.json_storage import JsonStorage

        item = data.get("item")
        json_path = data.get("json_path")

        if not item:
            return False, "没有可撤销的项"

        if json_path is None:
            json_path = Config.COMIC_DIR / "image_names.json"
        else:
            json_path = Path(json_path) if isinstance(json_path, str) else json_path

        JsonStorage.add_item(json_path, item)
        logger.info(f"撤销删除项: {item.get('name')}")
        return True, f"已撤销删除项: {item.get('name')}"
