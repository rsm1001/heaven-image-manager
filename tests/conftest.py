"""全局 conftest：路径注入、状态隔离、Qt 应用、logger 抑制。

设计原则：
1. 不修改任何业务源码。
2. 所有 IO 落到 pytest 的 tmp_path / tmp_path_factory，不污染仓库根。
3. 类级可变状态在每个 test function 之前 autouse 重置。
4. logger 不在仓库根 logs/ 写文件。
5. 把项目根 append 到 sys.path，让 import core.xxx / ui.xxx 可用。
"""
import logging
import os
import sys
from pathlib import Path

import pytest

# ----------------------------------------------------------------------
# 1. sys.path：让 "import core.xxx" / "import ui.xxx" 在没装包时也能解析
# ----------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ----------------------------------------------------------------------
# 2. 强制 Qt offscreen 平台（CI 与本地一致）。必须在 QApplication 之前。
# ----------------------------------------------------------------------
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# ----------------------------------------------------------------------
# 3. 把 utils.logger.setup_logger monkeypatch 掉，让它只返回 NullHandler logger，
#    避免在仓库根 logs/ 下生成时间戳文件。
# ----------------------------------------------------------------------
@pytest.fixture(autouse=True, scope="session")
def _silence_logger():
    import utils.logger as _logger_mod

    def _silent_setup(name="HeavenComic", level=logging.INFO):
        lg = logging.getLogger(name)
        lg.setLevel(level)
        # 防止重复添加
        if not lg.handlers:
            lg.addHandler(logging.NullHandler())
        return lg

    original = _logger_mod.setup_logger
    _logger_mod.setup_logger = _silent_setup
    # utils.logger 模块在 import 时已经把全局 logger 实例化过，替换 handler
    global_logger = _logger_mod.logger
    for h in list(global_logger.handlers):
        global_logger.removeHandler(h)
    global_logger.addHandler(logging.NullHandler())
    yield
    _logger_mod.setup_logger = original


# ----------------------------------------------------------------------
# 4. 把 Config 的所有路径类属性重定向到 function 级 tmp。
#    Config.* 是 class attribute，在 import 时已求值为 Path 对象，
#    因此必须显式重新赋值。
#
#    用 function scope 保证每个测试拿到一个全新的 tmp dir，
#    互不污染。session scope 会让先后两个 test 读到对方写下的 JSON。
# ----------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _config_paths(tmp_path, monkeypatch):
    from utils import config as config_mod

    base = tmp_path
    comic = base / "comic"
    target = comic / "101"
    trash = comic / "trash"

    monkeypatch.setattr(config_mod.Config, "BASE_DIR", base)
    monkeypatch.setattr(config_mod.Config, "COMIC_DIR", comic)
    monkeypatch.setattr(config_mod.Config, "TARGET_DIR", target)
    monkeypatch.setattr(config_mod.Config, "TRASH_DIR", trash)
    monkeypatch.setattr(config_mod.Config, "TRASH_RECORD_FILE", comic / "trash_records.json")
    monkeypatch.setattr(config_mod.Config, "DOWNLOAD_RECORD_FILE", comic / "download_records.json")
    monkeypatch.setattr(config_mod.Config, "CONFIG_FILE", base / "config.json")
    config_mod.Config.ensure_directories()

    yield {
        "base": base,
        "comic": comic,
        "target": target,
        "trash": trash,
    }

    # monkeypatch.undo() 由 pytest 自动调用


# ----------------------------------------------------------------------
# 5. 每个 test 之前重置类级可变状态。
# ----------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset_class_state(_config_paths):
    from core.undo_manager import UndoManager
    from core.manager_factory import ManagerFactory
    UndoManager.clear()
    ManagerFactory.reset()
    yield


# ----------------------------------------------------------------------
# 6. 提供一个统一获取 Config 路径的别名 fixture。
# ----------------------------------------------------------------------
@pytest.fixture
def config_paths(_config_paths):
    return _config_paths


# ----------------------------------------------------------------------
# 7. 提供一个隔离的 trash_records.json / image_names.json 路径。
# ----------------------------------------------------------------------
@pytest.fixture
def trash_records_path(config_paths):
    return config_paths["comic"] / "trash_records.json"


@pytest.fixture
def image_names_path(config_paths):
    return config_paths["comic"] / "image_names.json"


@pytest.fixture
def download_records_path(config_paths):
    return config_paths["comic"] / "download_records.json"
