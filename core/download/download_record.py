"""下载记录仓储（Repository 模式）。

负责 download_records.json 的读写与统计：加载、保存、清理上限、查询已完成/已存在 ID。
所有 IO 通过 Config.DOWNLOAD_RECORD_FILE 路径解耦，调用方无需关心存储细节。
"""
import json
from pathlib import Path
from typing import Dict, Set

from utils.config import Config
from utils.logger import logger


class DownloadRecordRepository:
    """下载记录仓储 - 线程安全的 JSON 持久化。

    暴露的接口以业务语义命名（load_all / save_all / completed_ids /
    existing_file_ids），与具体 JSON 结构解耦；外部仅依赖该接口，
    不再直接接触文件路径。
    """

    @staticmethod
    def load_all() -> Dict[int, dict]:
        """加载全部下载记录。键统一转为 int。"""
        record_file: Path = Config.DOWNLOAD_RECORD_FILE
        if not record_file.exists():
            return {}
        try:
            with open(record_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {int(k): v for k, v in data.items()}
        except (json.JSONDecodeError, OSError, ValueError) as e:
            logger.error(f"Failed to load download records: {e}")
            return {}

    @staticmethod
    def save_all(records: Dict[int, dict]) -> bool:
        """保存下载记录；超过上限时按"失败优先 + 时间最旧先删"策略清理。

        Returns:
            bool: 写入成功返回 True，失败返回 False。
        """
        if len(records) > Config.MAX_DOWNLOAD_RECORD_COUNT:
            # 按时间排序，优先删除失败记录，再删除最早的成功记录
            sorted_ids = sorted(
                records.keys(),
                key=lambda x: (
                    0 if records[x].get("status") == "failed" else 1,
                    records[x].get("downloaded_time", "") or records[x].get("failed_time", "")
                )
            )
            # 保留最新的 MAX_DOWNLOAD_RECORD_COUNT 条
            keep_ids = set(sorted_ids[-Config.MAX_DOWNLOAD_RECORD_COUNT:])
            records = {k: v for k, v in records.items() if k in keep_ids}
            logger.info(f"Download records trimmed to {len(records)} entries")

        try:
            with open(Config.DOWNLOAD_RECORD_FILE, "w", encoding="utf-8") as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
            return True
        except OSError as e:
            logger.error(f"Failed to save download records: {e}")
            return False

    @staticmethod
    def completed_ids() -> Set[int]:
        """获取已成功下载的 ID 集合。"""
        records = DownloadRecordRepository.load_all()
        return {img_id for img_id, rec in records.items() if rec.get("status") == "success"}

    @staticmethod
    def existing_file_ids() -> Set[int]:
        """扫描已存在的图片文件 ID。

        只把"文件存在 + 大小 > 0 + 后缀是图片"的算作有效；0 字节或 .part
        残留不会被当成成功，避免重复下载时静默跳过坏文件。
        """
        existing_ids: Set[int] = set()
        for ext in Config.IMAGE_EXTENSIONS:
            for p in Config.COMIC_DIR.glob(f"*{ext}"):
                # .part 是临时文件，跳过
                if p.suffix == ".part" or p.name.endswith(".part"):
                    continue
                try:
                    if p.stat().st_size <= 0:
                        continue
                    existing_ids.add(int(p.stem))
                except (ValueError, OSError):
                    continue
        return existing_ids

    # ------------------------------------------------------------------
    # 兼容旧 API（测试与历史调用方使用的方法名）
    # ------------------------------------------------------------------
    @staticmethod
    def load_records() -> Dict[int, dict]:
        """兼容旧 API：等价于 :meth:`load_all`。"""
        return DownloadRecordRepository.load_all()

    @staticmethod
    def save_records(records: Dict[int, dict]) -> bool:
        """兼容旧 API：等价于 :meth:`save_all`。"""
        return DownloadRecordRepository.save_all(records)

    @staticmethod
    def get_completed_ids() -> Set[int]:
        """兼容旧 API：等价于 :meth:`completed_ids`。"""
        return DownloadRecordRepository.completed_ids()

    @staticmethod
    def get_existing_file_ids() -> Set[int]:
        """兼容旧 API：等价于 :meth:`existing_file_ids`。"""
        return DownloadRecordRepository.existing_file_ids()
