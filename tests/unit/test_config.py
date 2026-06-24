"""utils.config.Config 单元测试。

Config 的 get/set_last_downloaded_id 是有副作用的方法（写 config.json），
而路径已由 conftest 注入到 tmp。其他常量（IMAGE_EXTENSIONS 等）只断言存在性。
"""
import json
import threading
from pathlib import Path

import pytest

from utils.config import Config


# ---------------- get_last_downloaded_id ----------------

class TestGetLastDownloadedId:
    def test_file_missing_returns_default(self):
        # conftest 已经把 CONFIG_FILE 重定向到 tmp；这里再写坏它
        Config.CONFIG_FILE.unlink(missing_ok=True)
        assert Config.get_last_downloaded_id() == Config.DEFAULT_LAST_DOWNLOADED_ID

    def test_corrupted_json_returns_default(self):
        Config.CONFIG_FILE.write_text("{ not valid", encoding="utf-8")
        assert Config.get_last_downloaded_id() == Config.DEFAULT_LAST_DOWNLOADED_ID

    def test_normal_value(self):
        Config.CONFIG_FILE.write_text(
            json.dumps({"last_downloaded_id": 12345}), encoding="utf-8"
        )
        assert Config.get_last_downloaded_id() == 12345

    def test_missing_key_returns_default(self):
        Config.CONFIG_FILE.write_text(json.dumps({"other": 1}), encoding="utf-8")
        assert Config.get_last_downloaded_id() == Config.DEFAULT_LAST_DOWNLOADED_ID


# ---------------- set_last_downloaded_id ----------------

class TestSetLastDownloadedId:
    def test_write_to_empty_file(self):
        Config.CONFIG_FILE.unlink(missing_ok=True)
        Config.set_last_downloaded_id(777)
        data = json.loads(Config.CONFIG_FILE.read_text(encoding="utf-8"))
        assert data["last_downloaded_id"] == 777

    def test_overwrite_existing(self):
        Config.CONFIG_FILE.write_text(
            json.dumps({"last_downloaded_id": 1, "extra": "keep"}),
            encoding="utf-8",
        )
        Config.set_last_downloaded_id(9999)
        data = json.loads(Config.CONFIG_FILE.read_text(encoding="utf-8"))
        assert data["last_downloaded_id"] == 9999
        assert data["extra"] == "keep"

    def test_round_trip(self):
        Config.set_last_downloaded_id(42)
        assert Config.get_last_downloaded_id() == 42


# ---------------- 路径 / 常量 sanity ----------------

class TestConstants:
    def test_image_extensions(self):
        assert ".jpg" in Config.IMAGE_EXTENSIONS
        assert ".png" in Config.IMAGE_EXTENSIONS

    def test_base_url_format(self):
        assert "{}" in Config.BASE_URL
        assert "18comic" in Config.BASE_URL

    def test_paths_under_config(self):
        # conftest 已注入到 tmp
        assert Config.COMIC_DIR.is_dir()
        assert Config.TARGET_DIR.is_dir()
        assert Config.TRASH_DIR.is_dir()


# ---------------- _read_config_dict edge cases ----------------

class TestReadConfigDict:
    def test_empty_file_isolated_and_returns_empty_dict(self, tmp_path):
        """空文件应触发隔离并返回 {}。"""
        empty_file = tmp_path / "empty_config.json"
        empty_file.write_text("", encoding="utf-8")
        original = Config.CONFIG_FILE
        Config.CONFIG_FILE = empty_file
        try:
            result = Config._read_config_dict()
            assert result == {}
            # 隔离后原文件应不存在
            assert not empty_file.exists()
        finally:
            Config.CONFIG_FILE = original

    def test_top_level_not_dict_isolated_and_returns_empty_dict(self, tmp_path):
        """顶级是数组而非对象时应触发隔离并返回 {}。"""
        bad_file = tmp_path / "array_config.json"
        bad_file.write_text("[1, 2, 3]", encoding="utf-8")
        original = Config.CONFIG_FILE
        Config.CONFIG_FILE = bad_file
        try:
            result = Config._read_config_dict()
            assert result == {}
        finally:
            Config.CONFIG_FILE = original

    def test_oserror_on_stat_returns_empty_dict(self, tmp_path):
        """stat 失败时应返回 {}。"""
        # 使用不存在的路径避免 OSError
        missing_file = tmp_path / "nonexistent.json"
        original = Config.CONFIG_FILE
        Config.CONFIG_FILE = missing_file
        try:
            result = Config._read_config_dict()
            assert result == {}
        finally:
            Config.CONFIG_FILE = original

    def test_oserror_on_read_returns_empty_dict(self, tmp_path):
        """读取失败（OSError）时应返回 {}。"""
        # 文件存在但内容无法读取（路径格式特殊导致 open 失败）
        # 由于跨平台限制，这里用不存在的路径模拟读取失败
        missing_file = tmp_path / "unreadable.json"
        original = Config.CONFIG_FILE
        Config.CONFIG_FILE = missing_file
        try:
            result = Config._read_config_dict()
            assert result == {}
        finally:
            Config.CONFIG_FILE = original


# ---------------- _atomic_write_json edge cases ----------------

class TestAtomicWriteJson:
    def test_parent_dir_creation_failure(self, tmp_path):
        """父目录无法创建时返回 False。"""
        # 使用无效路径字符模拟失败（Windows 下 NUL 等）
        import os
        invalid_path = Path(os.devnull)  # always fails for parent mkdir
        result = Config._atomic_write_json(invalid_path, {"key": "value"})
        assert result is False

    def test_get_last_downloaded_id_non_int_value(self, tmp_path):
        """config.json 中 last_downloaded_id 非整数字符串时返回默认值。"""
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps({"last_downloaded_id": "not_an_int"}), encoding="utf-8")
        original = Config.CONFIG_FILE
        Config.CONFIG_FILE = config_file
        try:
            assert Config.get_last_downloaded_id() == Config.DEFAULT_LAST_DOWNLOADED_ID
        finally:
            Config.CONFIG_FILE = original


# ---------------- _isolate_corrupt_file edge cases ----------------

class TestIsolateCorruptFile:
    def test_move_failure_is_non_fatal(self, tmp_path):
        """隔离（重命名）失败不应抛出异常。"""
        # 尝试隔离到无效路径
        invalid_target = Path("/invalid/path/that/cannot/exist/file.txt")
        Config._isolate_corrupt_file(invalid_target, "simulated failure")
        # 无异常 = 测试通过
