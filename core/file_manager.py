"""文件管理模块 - 核心文件操作功能"""
import os
import shutil
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
from datetime import datetime

from utils.logger import logger
from utils.config import Config
from core.undo_manager import UndoManager, UndoOperationType
from core.trash_manager import TrashManager
from core.json_storage import JsonStorage


class FileManager:
    """文件管理类 - 核心功能模块"""

    @staticmethod
    def ensure_directories() -> None:
        """确保必要的目录存在"""
        Config.ensure_directories()
        logger.info("目录初始化完成")

    # ==================== Undo/Redo 操作 ====================

    @classmethod
    def push_undo(cls, record: dict) -> None:
        """记录操作到历史栈（委托给UndoManager）"""
        UndoManager.push(record)

    @classmethod
    def undo(cls) -> Tuple[bool, str, Optional[dict]]:
        """执行撤销操作（委托给UndoManager）"""
        return UndoManager.undo()

    @classmethod
    def clear_undo_stack(cls) -> None:
        """清空操作历史（委托给UndoManager）"""
        UndoManager.clear()

    @classmethod
    def get_undo_stack_size(cls) -> int:
        """获取撤销栈大小"""
        return UndoManager.size()

    # ==================== 图片文件操作 ====================

    @staticmethod
    def get_image_files(directory: Optional[Path] = None) -> List[Path]:
        """获取图片文件列表（按名称排序）

        Args:
            directory: 目录路径，默认使用配置中的漫画目录

        Returns:
            图片文件路径列表
        """
        if directory is None:
            directory = Config.COMIC_DIR

        image_files = []

        if directory.exists():
            for ext in Config.IMAGE_EXTENSIONS:
                image_files.extend(directory.glob(f"*{ext}"))
                image_files.extend(directory.glob(f"*{ext.upper()}"))

        # 去重：使用文件名的绝对路径作为键来去重
        unique_files = []
        seen = set()

        for file_path in image_files:
            file_key = os.path.normcase(os.path.abspath(file_path))
            if file_key not in seen:
                seen.add(file_key)
                unique_files.append(file_path)

        # 按文件名排序
        return sorted(unique_files, key=lambda x: x.name.lower())

    @staticmethod
    def move_image(image_path: Path, target_dir: Optional[Path] = None) -> Tuple[bool, str, Optional[Path]]:
        """移动图片到目标目录

        Args:
            image_path: 图片路径
            target_dir: 目标目录，默认使用配置中的目标目录

        Returns:
            Tuple[bool, str, Optional[Path]]: (是否成功, 消息, 实际目标路径)
        """
        if target_dir is None:
            target_dir = Config.TARGET_DIR

        try:
            target_path = target_dir / image_path.name

            # 如果目标文件已存在，添加序号
            counter = 1
            while target_path.exists():
                name_parts = image_path.stem.split('_')
                if len(name_parts) > 1 and name_parts[-1].isdigit():
                    base_name = '_'.join(name_parts[:-1])
                else:
                    base_name = image_path.stem

                target_path = target_dir / f"{base_name}_{counter}{image_path.suffix}"
                counter += 1

            shutil.move(str(image_path), str(target_path))

            # 记录撤销操作
            FileManager.push_undo({
                "type": UndoOperationType.MOVE,
                "data": {"source": str(image_path), "target": str(target_path)}
            })

            logger.info(f"Moved image from {image_path} to {target_path}")
            return True, f"已移动到: {target_path.name}", target_path
        except Exception as e:
            logger.error(f"Failed to move image {image_path}: {e}")
            return False, f"移动失败: {e}", None

    @staticmethod
    def delete_image(image_path: Path) -> Tuple[bool, str]:
        """删除图片（移入垃圾桶）

        Args:
            image_path: 图片路径

        Returns:
            Tuple[bool, str]: (是否成功, 消息)
        """
        try:
            name = image_path.stem
            success, msg = TrashManager.add_to_trash(image_path)

            if success:
                # 记录撤销操作
                FileManager.push_undo({
                    "type": UndoOperationType.DELETE,
                    "data": {"name": name}
                })

            return success, msg
        except Exception as e:
            logger.error(f"Failed to delete image {image_path}: {e}")
            return False, f"删除失败: {e}"

    # ==================== 垃圾桶操作 ====================

    @staticmethod
    def get_trash_records() -> List[dict]:
        """获取所有垃圾桶记录"""
        return TrashManager.get_all_records()

    @staticmethod
    def restore_from_trash(name: str) -> Tuple[bool, str]:
        """从垃圾桶恢复图片"""
        return TrashManager.restore(name)

    @staticmethod
    def permanent_delete(name: str) -> Tuple[bool, str]:
        """永久删除图片"""
        return TrashManager.permanent_delete(name)

    @staticmethod
    def empty_trash() -> Tuple[bool, str]:
        """清空垃圾桶"""
        return TrashManager.empty()

    # ==================== JSON数据操作 ====================

    @staticmethod
    def load_json_data(json_path: Optional[Path] = None) -> List[dict]:
        """加载JSON数据

        Args:
            json_path: JSON文件路径，默认使用image_names.json

        Returns:
            JSON数据列表
        """
        if json_path is None:
            json_path = Config.COMIC_DIR / "image_names.json"
        return JsonStorage.load(json_path)

    @staticmethod
    def save_json_data(data: List[dict], json_path: Optional[Path] = None) -> bool:
        """保存JSON数据

        Args:
            data: 要保存的数据
            json_path: JSON文件路径，默认使用image_names.json

        Returns:
            是否保存成功
        """
        if json_path is None:
            json_path = Config.COMIC_DIR / "image_names.json"
        return JsonStorage.save(data, json_path)

    # ==================== 目录提取操作 ====================

    @staticmethod
    def extract_image_names_from_directory(
        source_dir: Path,
        append_mode: bool = True,
        delete_after_extract: bool = False
    ) -> Dict[str, Any]:
        """从指定目录提取图片名称

        Args:
            source_dir: 源图片目录路径
            append_mode: True=追加模式，False=覆盖模式
            delete_after_extract: True=提取后删除源文件，False=仅提取不删除

        Returns:
            包含操作结果的字典
        """
        try:
            if not source_dir.exists():
                return {"success": False, "message": f"目录不存在: {source_dir}"}

            if not source_dir.is_dir():
                return {"success": False, "message": f"路径不是目录: {source_dir}"}

            # 获取所有图片文件
            image_extensions = Config.IMAGE_EXTENSIONS
            image_files = []
            for file_path in source_dir.iterdir():
                if file_path.is_file() and file_path.suffix.lower() in image_extensions:
                    image_files.append(file_path)

            logger.info(f"Found {len(image_files)} image files in {source_dir}")

            if not image_files:
                return {"success": False, "message": "未找到图片文件"}

            # 提取文件名（不含扩展名）
            image_names = [file.stem for file in image_files]

            # 准备新项目
            new_items = []
            for name in image_names:
                new_items.append({
                    "name": name,
                    "source": str(source_dir.relative_to(Config.BASE_DIR)),
                    "extension": Path(name).suffix if Path(name).suffix else "",
                    "added_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })

            # 处理JSON数据
            json_path = Config.COMIC_DIR / "image_names.json"
            result = JsonStorage.append_items(json_path, new_items, append_mode)

            # 记录撤销操作
            if result.get("success") and result.get("added_items"):
                FileManager.push_undo({
                    "type": UndoOperationType.EXTRACT,
                    "data": {
                        "added_items": result["added_items"],
                        "json_path": str(json_path)
                    }
                })

            # 提取后直接删除源文件（可选）
            deleted_count = 0
            if delete_after_extract and result.get("success"):
                added_names = {item.get('name') for item in new_items}
                for file_path in image_files:
                    if file_path.stem in added_names:
                        try:
                            file_path.unlink()
                            deleted_count += 1
                            logger.info(f"提取后已直接删除源文件: {file_path.name}")
                        except Exception as e:
                            logger.error(f"删除源文件失败 {file_path.name}: {e}")

            result["deleted_count"] = deleted_count
            return result

        except Exception as e:
            logger.error(f"Error processing directory {source_dir}: {e}")
            return {"success": False, "message": f"处理过程中发生错误: {e}"}

    # ==================== 统计操作 ====================

    @staticmethod
    def get_stats() -> dict:
        """获取统计数据

        Returns:
            统计信息字典
        """
        json_path = Config.COMIC_DIR / "image_names.json"

        stats = {
            "file_exists": json_path.exists(),
            "item_count": 0,
            "json_path": str(json_path)
        }

        if json_path.exists():
            try:
                file_size = json_path.stat().st_size
                stats["file_size_kb"] = file_size / 1024
                stats["file_size_mb"] = file_size / (1024 * 1024)

                # 获取添加时间范围
                data = FileManager.load_json_data(json_path)
                if data:
                    times = [item.get("added_time") for item in data if item.get("added_time")]
                    if times:
                        stats["first_added"] = min(times)
                        stats["last_added"] = max(times)

                stats["item_count"] = len(data)
            except:
                stats["file_size_kb"] = 0
                stats["file_size_mb"] = 0

        return stats
