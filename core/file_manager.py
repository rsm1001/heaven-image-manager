"""文件管理模块"""
import os
import shutil
from pathlib import Path
from typing import List, Optional, Tuple
from PIL import Image
import json
from datetime import datetime
import sys
from pathlib import Path
# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.logger import logger
from utils.config import Config


class FileManager:
    """文件管理类"""

    @staticmethod
    def ensure_directories() -> None:
        """确保必要的目录存在"""
        Config.COMIC_DIR.mkdir(parents=True, exist_ok=True)
        Config.TARGET_DIR.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def get_image_files(directory: Optional[Path] = None) -> List[Path]:
        """获取图片文件列表（按名称排序）"""
        if directory is None:
            directory = Config.COMIC_DIR
        
        image_files = []
        
        if directory.exists():
            for ext in Config.IMAGE_EXTENSIONS:
                # 同时匹配小写和大写扩展名
                image_files.extend(directory.glob(f"*{ext}"))
                image_files.extend(directory.glob(f"*{ext.upper()}"))
        
        # 去重：使用文件名的绝对路径作为键来去重
        unique_files = []
        seen = set()
        
        for file_path in image_files:
            # 使用文件的绝对路径作为唯一标识
            file_key = os.path.normcase(os.path.abspath(file_path))
            if file_key not in seen:
                seen.add(file_key)
                unique_files.append(file_path)
        
        # 按文件名排序
        return sorted(unique_files, key=lambda x: x.name.lower())

    @staticmethod
    def move_image(image_path: Path, target_dir: Optional[Path] = None) -> Tuple[bool, str]:
        """移动图片到目标目录"""
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
            logger.info(f"Moved image from {image_path} to {target_path}")
            return True, f"已移动到: {target_path.name}"
        except Exception as e:
            logger.error(f"Failed to move image {image_path}: {str(e)}")
            return False, f"移动失败: {str(e)}"

    @staticmethod
    def delete_image(image_path: Path) -> Tuple[bool, str]:
        """删除图片"""
        try:
            image_path.unlink()
            logger.info(f"Deleted image: {image_path}")
            return True, "删除成功"
        except Exception as e:
            logger.error(f"Failed to delete image {image_path}: {str(e)}")
            return False, f"删除失败: {str(e)}"

    @staticmethod
    def load_json_data(json_path: Optional[Path] = None) -> List[dict]:
        """加载JSON数据"""
        if json_path is None:
            json_path = Config.COMIC_DIR / "image_names.json"
        
        if not json_path.exists():
            return []
        
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                logger.info(f"Loaded {len(data)} items from {json_path}")
                return data
        except Exception as e:
            logger.error(f"Failed to read JSON file {json_path}: {str(e)}")
            return []

    @staticmethod
    def save_json_data(data: List[dict], json_path: Optional[Path] = None) -> bool:
        """保存JSON数据"""
        if json_path is None:
            json_path = Config.COMIC_DIR / "image_names.json"
        
        try:
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved {len(data)} items to {json_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save JSON file {json_path}: {str(e)}")
            return False

    @staticmethod
    def extract_image_names_from_directory(source_dir: Path, 
                                         append_mode: bool = True) -> dict:
        """
        从指定目录提取图片名称
        
        Args:
            source_dir: 源图片目录路径
            append_mode: True=追加模式，False=覆盖模式
            
        Returns:
            包含操作结果的字典
        """
        try:
            if not source_dir.exists():
                return {"success": False, "message": f"目录不存在: {source_dir}"}
            
            if not source_dir.is_dir():
                return {"success": False, "message": f"路径不是目录: {source_dir}"}
            
            # 支持的图片格式
            image_extensions = Config.IMAGE_EXTENSIONS
            
            # 获取所有图片文件
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
            existing_data = FileManager.load_json_data(json_path)
            
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
                logger.info(f"Append mode: Added {len(filtered_new_items)} new items, skipped {len(new_items) - len(filtered_new_items)} duplicates")
            else:
                # 覆盖模式：清空原有数据
                updated_data = new_items
                logger.info(f"Overwrite mode: Added {len(new_items)} new items, cleared existing data")
            
            # 保存到JSON
            save_success = FileManager.save_json_data(updated_data, json_path)
            if not save_success:
                return {"success": False, "message": "保存JSON失败"}
            
            result_msg = f"成功提取 {len(new_items)} 个图片名称"
            if append_mode:
                result_msg += f"（追加模式）"
            else:
                result_msg += f"（覆盖模式）"
            
            return {
                "success": True,
                "message": result_msg,
                "added_count": len(new_items),
                "total_count": len(updated_data),
                "mode": "append" if append_mode else "overwrite"
            }
            
        except Exception as e:
            logger.error(f"Error processing directory {source_dir}: {str(e)}")
            return {"success": False, "message": f"处理过程中发生错误: {str(e)}"}

    @staticmethod
    def get_stats() -> dict:
        """获取统计数据"""
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