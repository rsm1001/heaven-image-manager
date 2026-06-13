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
