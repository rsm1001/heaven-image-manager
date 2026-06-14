"""日志工具模块"""
import logging
import logging.handlers
import os
import sys
import json
import re
import time
from datetime import datetime
from pathlib import Path

try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init(autoreset=True)
    COLORAMA_AVAILABLE = True
except ImportError:
    COLORAMA_AVAILABLE = False
    Fore = Style = None


# 默认日志配置
LOG_DIR = Path("logs")
LOG_FILE_NAME = "heaven_comic.log"
LOG_MAX_BYTES = 5 * 1024 * 1024  # 单文件 5MB
LOG_BACKUP_COUNT = 5             # 保留 5 个旧文件
LOG_MAX_AGE_DAYS = 30            # 30 天前的文件启动时清理


class JsonFormatter(logging.Formatter):
    """自定义JSON日志格式化器"""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": self.formatTime(record, self.datefmt),
            "name": record.name,
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_data, ensure_ascii=False)


class ColoredFormatter(logging.Formatter):
    """彩色控制台日志格式化器"""

    LEVEL_COLORS = {
        'DEBUG': 'cyan',
        'INFO': 'green',
        'WARNING': 'yellow',
        'ERROR': 'red',
        'CRITICAL': 'magenta',
    }

    def _get_color_codes(self, color_name: str) -> str:
        if not COLORAMA_AVAILABLE:
            return ''
        color_map = {
            'cyan': Fore.CYAN,
            'green': Fore.GREEN,
            'yellow': Fore.YELLOW,
            'red': Fore.RED,
            'magenta': Fore.MAGENTA,
            'blue': Fore.BLUE,
            'white': Fore.WHITE,
            'grey': Fore.LIGHTBLACK_EX,
        }
        return color_map.get(color_name, '')

    def _format_time(self, record: logging.LogRecord) -> str:
        ct = datetime.fromtimestamp(record.created)
        ms = f"{ct.microsecond // 1000:03d}"
        return f"{ct.strftime('%Y-%m-%d %H:%M:%S')}.{ms}"

    def _format_level(self, levelname: str) -> str:
        color = self.LEVEL_COLORS.get(levelname, 'white')
        color_code = self._get_color_codes(color)
        reset = Style.RESET_ALL if COLORAMA_AVAILABLE else ''
        return f"{color_code}{levelname:<5}{reset}"

    def _format_location(self, record: logging.LogRecord) -> str:
        color_code = self._get_color_codes('cyan') if COLORAMA_AVAILABLE else ''
        reset = Style.RESET_ALL if COLORAMA_AVAILABLE else ''
        return f"{color_code}{record.module}:{record.lineno}{reset}"

    def _colorize_message(self, message: str) -> str:
        if not COLORAMA_AVAILABLE:
            return message
        bright_white = f"{Style.BRIGHT}{Fore.WHITE}"
        blue = Fore.BLUE
        reset = Style.RESET_ALL
        pattern = r'(\w+)=(\S+)(?=\s+\w+=|$)'
        result = []
        last_end = 0
        for match in re.finditer(pattern, message):
            result.append(f"{bright_white}{message[last_end:match.start()]}")
            result.append(f"{blue}{match.group(1)}{reset}={match.group(2)}")
            last_end = match.end()
        result.append(f"{bright_white}{message[last_end:]}")
        return ''.join(result)

    def format(self, record: logging.LogRecord) -> str:
        time_str = self._format_time(record)
        level_str = self._format_level(record.levelname)
        location_str = self._format_location(record)
        message_str = self._colorize_message(record.getMessage())
        return f"{self._get_color_codes('grey')}{time_str}{Style.RESET_ALL if COLORAMA_AVAILABLE else ''} {level_str} {location_str} {message_str}"


def _purge_old_logs(log_dir: Path, max_age_days: int) -> int:
    """清理 max_age_days 天前的旧日志（RotatingFileHandler 不管 mtime）。"""
    if not log_dir.exists():
        return 0
    cutoff = time.time() - max_age_days * 86400
    cleaned = 0
    try:
        for p in log_dir.glob("*.log*"):
            try:
                if p.is_file() and p.stat().st_mtime < cutoff:
                    p.unlink()
                    cleaned += 1
            except OSError:
                continue
    except OSError:
        return cleaned
    return cleaned


def setup_logger(name: str = "HeavenComic", level: int = logging.INFO,
                 log_dir: Path = None,
                 max_bytes: int = LOG_MAX_BYTES,
                 backup_count: int = LOG_BACKUP_COUNT,
                 max_age_days: int = LOG_MAX_AGE_DAYS):
    """
    设置日志记录器

    改进点：
    1. 用 RotatingFileHandler 按大小切，不再每次启动新建时间戳文件
    2. 启动时清理 max_age_days 天前的旧文件，限制日志目录体积
    3. 单文件固定名 heaven_comic.log，旧文件自动改名 .log.1 ... .log.N
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # 防止重复添加处理器
    if logger.handlers:
        return logger

    # 控制台处理器
    try:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(ColoredFormatter())
        logger.addHandler(console_handler)
    except Exception:
        # 关闭阶段或无 stdout 的环境，console handler 可有可无
        pass

    # 文件处理器（按大小轮转）
    if log_dir is None:
        log_dir = LOG_DIR
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        log_dir = None

    if log_dir is not None:
        # 启动时清理过期旧文件
        try:
            _purge_old_logs(log_dir, max_age_days)
        except Exception:
            pass

        log_file = log_dir / LOG_FILE_NAME
        try:
            file_handler = logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding='utf-8',
            )
            file_handler.setFormatter(JsonFormatter())
            logger.addHandler(file_handler)
        except Exception:
            # 极端环境（只读 fs）下退化为不写文件
            pass

    return logger


# 全局日志实例
logger = setup_logger()
