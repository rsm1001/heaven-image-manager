"""日志工具模块"""
import logging
import sys
import json
import re
from datetime import datetime
from pathlib import Path

try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init(autoreset=True)
    COLORAMA_AVAILABLE = True
except ImportError:
    COLORAMA_AVAILABLE = False
    Fore = Style = None


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


def setup_logger(name: str = "HeavenComic", level: int = logging.INFO):
    """
    设置日志记录器
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # 防止重复添加处理器
    if logger.handlers:
        return logger
    
    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(ColoredFormatter())
    logger.addHandler(console_handler)
    
    # 文件处理器
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(JsonFormatter())
    logger.addHandler(file_handler)
    
    return logger


# 全局日志实例
logger = setup_logger()