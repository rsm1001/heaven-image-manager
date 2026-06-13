"""core.json_storage.JsonStorage 单元测试。"""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from core.json_storage import JsonStorage


# ---------------- load ----------------

class TestLoad:
    def test_file_not_exists_returns_empty(self, tmp_path):
        assert JsonStorage.load(tmp_path / "nope.json") == []

    def test_normal_json_round_trip(self, tmp_path):
        path = tmp_path / "data.json"
        data = [{"name": "a"}, {"name": "b"}]
        path.write_text(json.dumps(data), encoding="utf-8")
        assert JsonStorage.load(path) == data

    def test_corrupted_json_returns_empty(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{ not valid json", encoding="utf-8")
        assert JsonStorage.load(path) == []

    def test_permission_error_returns_empty(self, tmp_path):
        path = tmp_path / "perm.json"
        path.write_text("[]", encoding="utf-8")
        with patch("builtins.open", side_effect=PermissionError("denied")):
            assert JsonStorage.load(path) == []


# ---------------- save ----------------

class TestSave:
    def test_save_success_creates_file(self, tmp_path):
        path = tmp_path / "out" / "data.json"
        data = [{"name": "a"}]
        assert JsonStorage.save(data, path) is True
        assert path.exists()
        assert json.loads(path.read_text(encoding="utf-8")) == data

    def test_save_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "deep" / "nested" / "data.json"
        assert JsonStorage.save([{"x": 1}], path) is True
        assert path.exists()

    def test_save_write_failure_returns_false(self, tmp_path):
        path = tmp_path / "out.json"
        with patch("builtins.open", side_effect=OSError("disk full")):
            assert JsonStorage.save([{"x": 1}], path) is False


# ---------------- append_items ----------------

class TestAppendItems:
    def test_append_to_empty_file(self, image_names_path):
        items = [{"name": "a"}, {"name": "b"}, {"name": "c"}]
        result = JsonStorage.append_items(image_names_path, items, append_mode=True)
        assert result["success"] is True
        assert result["added_count"] == 3
        assert result["total_count"] == 3
        assert result["mode"] == "append"
        assert JsonStorage.load(image_names_path) == items

    def test_append_dedupes_by_name(self, image_names_path):
        existing = [{"name": "a"}, {"name": "b"}]
        JsonStorage.save(existing, image_names_path)
        new_items = [{"name": "a"}, {"name": "b"}, {"name": "c"}]
        result = JsonStorage.append_items(image_names_path, new_items, append_mode=True)
        assert result["added_count"] == 1
        assert result["total_count"] == 3
        names = {x["name"] for x in JsonStorage.load(image_names_path)}
        assert names == {"a", "b", "c"}

    def test_overwrite_mode_replaces(self, image_names_path):
        existing = [{"name": "old1"}, {"name": "old2"}]
        JsonStorage.save(existing, image_names_path)
        new_items = [{"name": "new1"}]
        result = JsonStorage.append_items(image_names_path, new_items, append_mode=False)
        assert result["added_count"] == 1
        assert result["total_count"] == 1
        assert JsonStorage.load(image_names_path) == new_items
        assert result["mode"] == "overwrite"

    def test_save_failure_returns_failure_dict(self, image_names_path):
        with patch.object(JsonStorage, "save", return_value=False):
            result = JsonStorage.append_items(
                image_names_path, [{"name": "x"}], append_mode=True
            )
        assert result["success"] is False
        assert "保存JSON失败" in result["message"]


# ---------------- remove_items_by_names ----------------

class TestRemoveItemsByNames:
    def test_remove_subset(self, image_names_path):
        items = [{"name": "a"}, {"name": "b"}, {"name": "c"}]
        JsonStorage.save(items, image_names_path)
        assert JsonStorage.remove_items_by_names(image_names_path, {"a", "c"}) is True
        assert JsonStorage.load(image_names_path) == [{"name": "b"}]

    def test_remove_empty_set_is_noop(self, image_names_path):
        items = [{"name": "a"}, {"name": "b"}]
        JsonStorage.save(items, image_names_path)
        assert JsonStorage.remove_items_by_names(image_names_path, set()) is True
        assert JsonStorage.load(image_names_path) == items

    def test_remove_all(self, image_names_path):
        items = [{"name": "a"}, {"name": "b"}]
        JsonStorage.save(items, image_names_path)
        assert JsonStorage.remove_items_by_names(image_names_path, {"a", "b"}) is True
        assert JsonStorage.load(image_names_path) == []


# ---------------- add_item ----------------

class TestAddItem:
    def test_add_single_item(self, image_names_path):
        JsonStorage.save([{"name": "a"}], image_names_path)
        assert JsonStorage.add_item(image_names_path, {"name": "b"}) is True
        assert JsonStorage.load(image_names_path) == [{"name": "a"}, {"name": "b"}]

    def test_add_to_empty_file(self, image_names_path):
        assert JsonStorage.add_item(image_names_path, {"name": "x"}) is True
        assert JsonStorage.load(image_names_path) == [{"name": "x"}]
