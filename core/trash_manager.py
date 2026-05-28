"""垃圾桶管理模块 - 负责图片的删除、恢复、永久删除等操作"""
import shutil
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any
from datetime import datetime

from utils.logger import logger
from utils.config import Config
from core.json_storage import JsonStorage


class TrashManager:
    """垃圾桶管理类"""

    @staticmethod
    def _load_records() -> List[dict]:
        """加载垃圾桶记录"""
        return JsonStorage.load(Config.TRASH_RECORD_FILE)

    @staticmethod
    def _save_records(records: List[dict]) -> bool:
        """保存垃圾桶记录"""
        return JsonStorage.save(records, Config.TRASH_RECORD_FILE)

    @staticmethod
    def add_to_trash(image_path: Path) -> Tuple[bool, str]:
        """将图片移入垃圾桶

        Args:
            image_path: 图片路径

        Returns:
            Tuple[bool, str]: (是否成功, 消息)
        """
        try:
            # 获取文件大小
            file_size = image_path.stat().st_size

            # 读取现有记录
            records = TrashManager._load_records()

            # 构建新记录
            new_record = {
                "name": image_path.stem,
                "extension": image_path.suffix,
                "original_path": str(image_path.relative_to(Config.COMIC_DIR)),
                "deleted_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "file_size": file_size
            }
            records.append(new_record)

            # 超出数量限制时删除最久的
            while len(records) > Config.MAX_TRASH_COUNT:
                records.sort(key=lambda x: x.get("deleted_time", ""))
                oldest = records.pop(0)
                oldest_file = Config.TRASH_DIR / f"{oldest['name']}{oldest.get('extension', '')}"
                if oldest_file.exists():
                    oldest_file.unlink()
                    logger.info(f"自动清理最久记录: {oldest['name']}")

            # 保存记录
            TrashManager._save_records(records)

            # 移动文件到垃圾桶目录
            target_path = Config.TRASH_DIR / image_path.name
            counter = 1
            while target_path.exists():
                target_path = Config.TRASH_DIR / f"{image_path.stem}_{counter}{image_path.suffix}"
                counter += 1

            shutil.move(str(image_path), str(target_path))
            logger.info(f"图片已移入垃圾桶: {image_path} -> {target_path}")
            return True, "已移入垃圾桶"
        except Exception as e:
            logger.error(f"Failed to delete image {image_path}: {e}")
            return False, f"删除失败: {e}"

    @staticmethod
    def get_all_records() -> List[dict]:
        """获取所有垃圾桶记录"""
        return TrashManager._load_records()

    @staticmethod
    def restore(name: str) -> Tuple[bool, str]:
        """从垃圾桶恢复图片

        Args:
            name: 图片名称（不含扩展名）

        Returns:
            Tuple[bool, str]: (是否成功, 消息)
        """
        try:
            records = TrashManager._load_records()

            # 查找对应记录
            target_record = None
            for i, record in enumerate(records):
                if record.get("name") == name:
                    target_record = record
                    records.pop(i)
                    break

            if not target_record:
                return False, "记录不存在"

            # 找到垃圾桶中的文件
            trash_file = None
            for ext in Config.IMAGE_EXTENSIONS:
                candidate = Config.TRASH_DIR / f"{name}{ext}"
                if candidate.exists():
                    trash_file = candidate
                    break

            if not trash_file:
                return False, f"找不到文件: {name}"

            # 恢复到原始位置
            original_path = Config.COMIC_DIR / target_record.get("original_path", name)
            original_path.parent.mkdir(parents=True, exist_ok=True)

            # 处理重名
            target_path = original_path
            counter = 1
            while target_path.exists():
                stem = original_path.stem
                parent = original_path.parent
                target_path = parent / f"{stem}_{counter}{original_path.suffix}"
                counter += 1

            shutil.move(str(trash_file), str(target_path))

            # 保存更新后的记录
            TrashManager._save_records(records)

            logger.info(f"已恢复图片: {name} -> {target_path}")
            return True, f"已恢复: {target_path.name}"
        except Exception as e:
            logger.error(f"Failed to restore from trash: {e}")
            return False, f"恢复失败: {e}"

    @staticmethod
    def permanent_delete(name: str) -> Tuple[bool, str]:
        """永久删除图片

        Args:
            name: 图片名称（不含扩展名）

        Returns:
            Tuple[bool, str]: (是否成功, 消息)
        """
        try:
            records = TrashManager._load_records()

            # 查找对应记录
            target_record = None
            for i, record in enumerate(records):
                if record.get("name") == name:
                    target_record = record
                    records.pop(i)
                    break

            if not target_record:
                return False, "记录不存在"

            # 删除物理文件
            for ext in Config.IMAGE_EXTENSIONS:
                trash_file = Config.TRASH_DIR / f"{name}{ext}"
                if trash_file.exists():
                    trash_file.unlink()
                    logger.info(f"永久删除: {trash_file}")
                    break

            # 保存更新后的记录
            TrashManager._save_records(records)

            return True, "已永久删除"
        except Exception as e:
            logger.error(f"Failed to permanent delete: {e}")
            return False, f"永久删除失败: {e}"

    @staticmethod
    def empty() -> Tuple[bool, str]:
        """清空垃圾桶

        Returns:
            Tuple[bool, str]: (是否成功, 消息)
        """
        try:
            records = TrashManager._load_records()

            # 删除所有物理文件
            for record in records:
                name = record.get("name")
                for ext in Config.IMAGE_EXTENSIONS:
                    trash_file = Config.TRASH_DIR / f"{name}{ext}"
                    if trash_file.exists():
                        trash_file.unlink()

            # 清空记录
            TrashManager._save_records([])

            logger.info("垃圾桶已清空")
            return True, "垃圾桶已清空"
        except Exception as e:
            logger.error(f"Failed to empty trash: {e}")
            return False, f"清空失败: {e}"
