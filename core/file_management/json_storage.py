"""JSON数据存储模块 - 负责JSON文件的读写操作"""
import json
import threading
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime

from utils.logger import logger


class JsonStorage:
    """JSON数据存储类 - 线程安全"""

    _lock = threading.Lock()

    @classmethod
    def load(cls, json_path: Path) -> List[Dict[str, Any]]:
        """加载JSON数据"""
        if not json_path.exists():
            return []

        with cls._lock:
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    logger.info(f"Loaded {len(data)} items from {json_path}")
                    return data
            except json.JSONDecodeError as e:
                logger.error(f"JSON decode error in {json_path}: {e}")
                return []
            except Exception as e:
                logger.error(f"Failed to read JSON file {json_path}: {e}")
                return []

    @classmethod
    def save(cls, data: List[Dict[str, Any]], json_path: Path) -> bool:
        """保存JSON数据"""
        with cls._lock:
            try:
                # 确保目录存在
                json_path.parent.mkdir(parents=True, exist_ok=True)
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                logger.info(f"Saved {len(data)} items to {json_path}")
                return True
            except Exception as e:
                logger.error(f"Failed to save JSON file {json_path}: {e}")
                return False

    @classmethod
    def append_items(cls, json_path: Path, new_items: List[Dict[str, Any]],
                     append_mode: bool = True) -> Dict[str, Any]:
        """追加或覆盖JSON数据

        Args:
            json_path: JSON文件路径
            new_items: 新增的数据项
            append_mode: True=追加模式，False=覆盖模式

        Returns:
            操作结果字典
        """
        existing_data = cls.load(json_path)

        if append_mode:
            # 追加模式：去重后添加
            existing_names = {item.get('name') for item in existing_data if isinstance(item, dict)}

            filtered_new_items = []
            for item in new_items:
                if item["name"] not in existing_names:
                    filtered_new_items.append(item)
                else:
                    logger.info(f"Skipping duplicate: {item['name']}")

            updated_data = existing_data + filtered_new_items
            result_msg = f"追加模式: 添加 {len(filtered_new_items)} 项，跳过 {len(new_items) - len(filtered_new_items)} 项重复"
            logger.info(result_msg)
            final_added_items = filtered_new_items
        else:
            # 覆盖模式：清空原有数据
            updated_data = new_items
            result_msg = f"覆盖模式: 添加 {len(new_items)} 项，清空现有数据"
            logger.info(result_msg)
            final_added_items = new_items

        save_success = cls.save(updated_data, json_path)
        if not save_success:
            return {"success": False, "message": "保存JSON失败"}

        return {
            "success": True,
            "message": result_msg,
            "added_count": len(final_added_items),
            "added_items": final_added_items,
            "total_count": len(updated_data),
            "mode": "append" if append_mode else "overwrite"
        }

    @classmethod
    def remove_items_by_names(cls, json_path: Path, names: set) -> bool:
        """根据名称集合移除JSON中的项"""
        existing_data = cls.load(json_path)
        updated_data = [item for item in existing_data if item.get("name") not in names]
        return cls.save(updated_data, json_path)

    @classmethod
    def add_item(cls, json_path: Path, item: Dict[str, Any]) -> bool:
        """添加单个JSON项"""
        existing_data = cls.load(json_path)
        existing_data.append(item)
        return cls.save(existing_data, json_path)
