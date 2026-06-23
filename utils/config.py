"""配置管理模块"""
import json
import os
import shutil
import tempfile
import threading
import uuid
from datetime import datetime
from pathlib import Path


def _load_env_file(env_path: Path) -> None:
    """加载 .env 文件中的键值对到 os.environ（不覆盖已有变量）。"""
    if not env_path.exists():
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError:
        # 读取失败不应影响程序启动
        pass


# 启动时静默加载项目根目录的 .env，避免硬编码代理等敏感信息
_load_env_file(Path(__file__).parent.parent / ".env")


class Config:
    """配置类 - 统一管理所有配置"""

    # 项目根目录
    BASE_DIR = Path(__file__).parent.parent

    # 图片扩展名
    IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}

    # 目录配置
    COMIC_DIR = BASE_DIR / "comic"
    TARGET_DIR = COMIC_DIR / "101"

    # 窗口配置
    WINDOW_TITLE = "天堂图片管理器 - PyQt版"
    WINDOW_WIDTH = 900
    WINDOW_HEIGHT = 700
    CENTER_ON_SCREEN = True

    # 图片显示配置
    MAX_IMAGE_WIDTH = 800
    MAX_IMAGE_HEIGHT = 550
    SLIDE_INTERVAL_MS = 3000

    # 下载配置
    DEFAULT_START_ID = 9009  # SpinBox 默认起始ID的 fallback 值
    DEFAULT_LAST_DOWNLOADED_ID = 9008  # config.json 读取失败时的默认值
    TOTAL_COUNT = 450
    RETRY_TIMES = 3
    RETRY_DELAY = 15
    REQUEST_DELAY = 2
    PROXY_RETRY_TIMES = 10
    PROXY_RETRY_DELAY = 20
    MAX_DOWNLOAD_WORKERS = 5
    BASE_URL = "https://cdn-msp.18comic.vip/media/albums/{}.jpg?u=1682391243"

    # 垃圾桶配置
    TRASH_DIR = COMIC_DIR / "trash"
    TRASH_RECORD_FILE = COMIC_DIR / "trash_records.json"
    MAX_TRASH_COUNT = 1000

    # 下载记录配置
    DOWNLOAD_RECORD_FILE = COMIC_DIR / "download_records.json"
    MAX_DOWNLOAD_RECORD_COUNT = 5000

    # config.json 路径
    CONFIG_FILE = BASE_DIR / "config.json"

    # 下载最小合法字节数（小于此值视为下载未完成/损坏）
    MIN_VALID_DOWNLOAD_BYTES = 1024

    # 代理配置（从环境变量读取，避免硬编码；可放 .env）
    PROXY_HTTP = os.getenv("PROXY_HTTP", "")
    PROXY_HTTPS = os.getenv("PROXY_HTTPS", "")

    # HTTP 请求头配置（外部服务 UA/Referer，便于在 .env 覆盖）
    DOWNLOAD_USER_AGENT = os.getenv(
        "DOWNLOAD_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
    )
    DOWNLOAD_REFERER = os.getenv("DOWNLOAD_REFERER", "https://18comic.vip/")

    # 线程安全锁：覆盖 Config 内所有 IO 路径，与 JsonStorage 协调
    _lock = threading.RLock()

    @classmethod
    def ensure_directories(cls):
        """确保必要目录存在"""
        cls.COMIC_DIR.mkdir(parents=True, exist_ok=True)
        cls.TARGET_DIR.mkdir(parents=True, exist_ok=True)
        cls.TRASH_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 内部工具：原子写 + 损坏隔离
    # ------------------------------------------------------------------
    @classmethod
    def _isolate_corrupt_file(cls, target: Path, reason: str) -> None:
        """把损坏/空的目标文件重命名为带时间戳的备份，避免污染下次启动。"""
        try:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup = target.with_name(f"{target.name}.broken-{ts}-{uuid.uuid4().hex[:6]}")
            shutil.move(str(target), str(backup))
            # 仅在已经导入 logger 的情况下输出，避免循环依赖
            try:
                from utils.logger import logger
                logger.warning(
                    f"已隔离损坏文件 {target.name} -> {backup.name} (原因: {reason})"
                )
            except Exception:
                pass
        except Exception:
            # 隔离失败也不致命，下次启动仍能再次尝试
            pass

    @classmethod
    def _read_config_dict(cls) -> dict:
        """读取并解析 config.json；遇到损坏/空文件就隔离 + 返回空 dict。"""
        if not cls.CONFIG_FILE.exists():
            return {}

        # 空文件：直接隔离
        try:
            if cls.CONFIG_FILE.stat().st_size == 0:
                cls._isolate_corrupt_file(cls.CONFIG_FILE, "empty file")
                return {}
        except OSError:
            return {}

        try:
            with open(cls.CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                cls._isolate_corrupt_file(cls.CONFIG_FILE, "top-level not object")
                return {}
            return data
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as e:
            cls._isolate_corrupt_file(cls.CONFIG_FILE, f"json decode error: {e}")
            return {}
        except OSError:
            return {}

    @classmethod
    def _atomic_write_json(cls, target: Path, data: dict) -> bool:
        """把 dict 原子写入 target：先写同名 .tmp，再 os.replace。

        os.replace 在 Windows 和 POSIX 都是原子的（POSIX 是 rename(2)，
        Windows 是 MoveFileEx with REPLACE_EXISTING），从而避免半行 JSON
        导致的"读-改-写"竞争窗口。
        """
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            return False

        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(
                prefix=target.name + ".",
                suffix=".tmp",
                dir=str(target.parent),
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)
                    f.flush()
                    try:
                        os.fsync(f.fileno())
                    except OSError:
                        # 某些 fs 不支持 fsync，忽略即可
                        pass
            except Exception:
                # 写 .tmp 失败，确保关闭并清理
                try:
                    os.close(fd)
                except OSError:
                    pass
                raise

            # 原子替换
            os.replace(tmp_path, target)
            return True
        except Exception:
            return False
        finally:
            if tmp_path is not None:
                try:
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
                except OSError:
                    pass

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------
    @classmethod
    def get_last_downloaded_id(cls) -> int:
        """从 config.json 读取 last_downloaded_id，失败时返回默认值。

        失败时（包括文件不存在/空/损坏）会先尝试隔离损坏文件，避免下次启动
        继续读到半行 JSON。
        """
        with cls._lock:
            data = cls._read_config_dict()
            value = data.get("last_downloaded_id", cls.DEFAULT_LAST_DOWNLOADED_ID)
            try:
                return int(value)
            except (TypeError, ValueError):
                return cls.DEFAULT_LAST_DOWNLOADED_ID

    @classmethod
    def set_last_downloaded_id(cls, value: int) -> bool:
        """写入 config.json 的 last_downloaded_id（原子写）。"""
        with cls._lock:
            data = cls._read_config_dict()
            data["last_downloaded_id"] = int(value)
            return cls._atomic_write_json(cls.CONFIG_FILE, data)


# 确保目录存在
Config.ensure_directories()
