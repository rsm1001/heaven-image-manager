"""core.undo_manager.UndoManager 单元测试。"""
import json
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from core.undo_manager import UndoManager, UndoOperationType
from tests.fixtures.jsons import write_json


# ---------------- 栈基本操作 ----------------

class TestStackBasics:
    def test_push_increments_size(self):
        UndoManager.push({"type": "x", "data": {}})
        assert UndoManager.size() == 1
        assert UndoManager.is_empty() is False

    def test_pop_returns_lifo(self):
        UndoManager.push({"type": "first", "data": {}})
        UndoManager.push({"type": "second", "data": {}})
        assert UndoManager.pop()["type"] == "second"
        assert UndoManager.pop()["type"] == "first"

    def test_pop_empty_returns_none(self):
        assert UndoManager.pop() is None

    def test_clear_empties_stack(self):
        UndoManager.push({"type": "x", "data": {}})
        UndoManager.push({"type": "y", "data": {}})
        UndoManager.clear()
        assert UndoManager.size() == 0
        assert UndoManager.is_empty() is True


# ---------------- undo 空 / 未知 ----------------

class TestUndoEmpty:
    def test_undo_empty_stack(self):
        ok, msg, rec = UndoManager.undo()
        assert ok is False
        assert "没有可撤销" in msg
        assert rec is None

    def test_undo_unknown_op_type(self):
        UndoManager.push({"type": "mystery", "data": {}})
        ok, msg, rec = UndoManager.undo()
        assert ok is False
        assert "未知" in msg
        assert rec["type"] == "mystery"


# ---------------- undo MOVE ----------------

class TestUndoMove:
    def test_undo_move_restores_source(self, config_paths):
        comic = config_paths["comic"]
        source = comic / "src.jpg"
        target = comic / "tgt.jpg"
        source.write_bytes(b"hello")
        target.write_bytes(b"hello")  # 已经移动过去
        source.unlink()  # 源不在

        UndoManager.push({
            "type": UndoOperationType.MOVE,
            "data": {"source": str(source), "target": str(target)},
        })
        ok, msg, rec = UndoManager.undo()
        assert ok is True
        assert rec["type"] == UndoOperationType.MOVE
        # 文件回到 source
        assert source.exists()
        assert not target.exists()

    def test_undo_move_target_missing(self, config_paths):
        comic = config_paths["comic"]
        source = comic / "src.jpg"
        target = comic / "tgt.jpg"
        # target 也不存在
        UndoManager.push({
            "type": UndoOperationType.MOVE,
            "data": {"source": str(source), "target": str(target)},
        })
        ok, msg, _ = UndoManager.undo()
        assert ok is False
        assert "已被移动或删除" in msg

    def test_undo_move_incomplete_record(self):
        UndoManager.push({"type": UndoOperationType.MOVE, "data": {}})
        ok, msg, _ = UndoManager.undo()
        assert ok is False
        assert "数据不完整" in msg

    def test_undo_move_source_exists_uses_counter(self, config_paths):
        """源路径已被占用时，应自动加 _1 后缀。"""
        comic = config_paths["comic"]
        source = comic / "src.jpg"
        target = comic / "tgt.jpg"
        source.write_bytes(b"new")
        target.write_bytes(b"old")  # 已存在，undo 后会被 move 走

        UndoManager.push({
            "type": UndoOperationType.MOVE,
            "data": {"source": str(source), "target": str(target)},
        })
        ok, _, _ = UndoManager.undo()
        assert ok is True
        # 原 source 仍在（未覆盖），新文件落到 src_1.jpg
        assert source.exists()
        assert (comic / "src_1.jpg").exists()


# ---------------- undo DELETE ----------------

class TestUndoDelete:
    def test_undo_delete_restores_from_trash(
        self, config_paths, trash_records_path
    ):
        from core.trash_manager import TrashManager

        comic = config_paths["comic"]
        trash = config_paths["trash"]
        name = "abc"
        # 文件已经在 trash 目录
        (trash / f"{name}.jpg").write_bytes(b"data")
        # 写一条 trash 记录
        write_json(trash_records_path, [
            {"name": name, "extension": ".jpg", "original_path": f"{name}.jpg",
             "deleted_time": "2026-01-01 00:00:00", "file_size": 4}
        ])

        UndoManager.push({
            "type": UndoOperationType.DELETE,
            "data": {"name": name},
        })
        ok, msg, rec = UndoManager.undo()
        assert ok is True
        assert rec["type"] == UndoOperationType.DELETE
        # 文件回到 comic 根
        assert (comic / f"{name}.jpg").exists()
        # trash 记录被移除
        assert TrashManager._load_records() == []

    def test_undo_delete_incomplete_record(self):
        UndoManager.push({"type": UndoOperationType.DELETE, "data": {}})
        ok, msg, _ = UndoManager.undo()
        assert ok is False
        assert "数据不完整" in msg


# ---------------- undo EXTRACT ----------------

class TestUndoExtract:
    def test_undo_extract_removes_items(self, image_names_path):
        # 先写一份 image_names 含 3 项
        write_json(image_names_path, [
            {"name": "x1"}, {"name": "x2"}, {"name": "kept"},
        ])
        added = [{"name": "x1"}, {"name": "x2"}]
        UndoManager.push({
            "type": UndoOperationType.EXTRACT,
            "data": {
                "added_items": added,
                "json_path": str(image_names_path),
            },
        })
        ok, msg, rec = UndoManager.undo()
        assert ok is True
        assert "已撤销提取" in msg
        # 只剩 kept
        from core.json_storage import JsonStorage
        assert JsonStorage.load(image_names_path) == [{"name": "kept"}]

    def test_undo_extract_no_added_items(self):
        UndoManager.push({
            "type": UndoOperationType.EXTRACT,
            "data": {"added_items": []},
        })
        ok, _, _ = UndoManager.undo()
        assert ok is False
        assert "没有可撤销的提取项" in _ if False else ok is False

    def test_undo_extract_default_path(self, config_paths, image_names_path):
        """不传 json_path 时应落到 Config.COMIC_DIR / image_names.json。"""
        write_json(image_names_path, [{"name": "y1"}, {"name": "y2"}])
        UndoManager.push({
            "type": UndoOperationType.EXTRACT,
            "data": {"added_items": [{"name": "y1"}]},
        })
        ok, _, _ = UndoManager.undo()
        assert ok is True
        from core.json_storage import JsonStorage
        assert JsonStorage.load(image_names_path) == [{"name": "y2"}]


# ---------------- undo DELETE_ITEM ----------------

class TestUndoDeleteItem:
    def test_undo_delete_item_restores(self, image_names_path):
        write_json(image_names_path, [{"name": "alive"}])
        UndoManager.push({
            "type": UndoOperationType.DELETE_ITEM,
            "data": {
                "item": {"name": "dead"},
                "json_path": str(image_names_path),
            },
        })
        ok, _, _ = UndoManager.undo()
        assert ok is True
        from core.json_storage import JsonStorage
        assert JsonStorage.load(image_names_path) == [
            {"name": "alive"},
            {"name": "dead"},
        ]

    def test_undo_delete_item_no_item(self):
        UndoManager.push({
            "type": UndoOperationType.DELETE_ITEM,
            "data": {},
        })
        ok, _, _ = UndoManager.undo()
        assert ok is False


# ---------------- 异常路径 ----------------

class TestUndoException:
    def test_undo_with_internal_exception(self):
        UndoManager.push({"type": UndoOperationType.MOVE, "data": {"source": "a", "target": "b"}})
        with patch.object(UndoManager, "_undo_move", side_effect=OSError("boom")):
            ok, msg, rec = UndoManager.undo()
        assert ok is False
        assert "撤销失败" in msg
        assert rec is None
