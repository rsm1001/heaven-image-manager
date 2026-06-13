"""core.file_manager.FileManager 单元测试。

FileManager 几乎全部是 delegate（委托给 UndoManager / TrashManager / JsonStorage），
测试重点是：
1. delegate 行为与下游一致
2. 副作用（文件移动 / 撤销栈增长）正确
3. 默认路径 / 显式路径分支
"""
import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from core.file_manager import FileManager
from core.undo_manager import UndoManager, UndoOperationType
from core.trash_manager import TrashManager
from core.json_storage import JsonStorage
from tests.fixtures.jsons import write_json, sample_image_records


def _jpg_bytes() -> bytes:
    img = Image.new("RGB", (1, 1), (255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


# ---------------- 目录 / 撤销 delegate ----------------

class TestEnsureDirectories:
    def test_creates_all_dirs(self, config_paths):
        FileManager.ensure_directories()
        for k in ("comic", "target", "trash"):
            assert config_paths[k].exists()


class TestUndoDelegate:
    def test_push_undo_goes_to_undo_manager(self):
        FileManager.push_undo({"type": "x", "data": {}})
        assert UndoManager.size() == 1
        assert UndoManager.pop()["type"] == "x"

    def test_undo_delegates(self):
        FileManager.push_undo({"type": "x", "data": {}})
        ok, _, rec = FileManager.undo()
        assert ok is False  # x 是未知类型

    def test_clear_undo_stack(self):
        FileManager.push_undo({"type": "x", "data": {}})
        FileManager.clear_undo_stack()
        assert UndoManager.size() == 0

    def test_get_undo_stack_size(self):
        FileManager.push_undo({"type": "a", "data": {}})
        FileManager.push_undo({"type": "b", "data": {}})
        assert FileManager.get_undo_stack_size() == 2


# ---------------- get_image_files ----------------

class TestGetImageFiles:
    def test_dir_not_exists(self, tmp_path):
        assert FileManager.get_image_files(tmp_path / "nope") == []

    def test_dir_empty(self, config_paths):
        assert FileManager.get_image_files(config_paths["comic"]) == []

    def test_returns_sorted_png_jpg(self, config_paths):
        comic = config_paths["comic"]
        (comic / "b.jpg").write_bytes(_jpg_bytes())
        (comic / "a.jpg").write_bytes(_jpg_bytes())
        (comic / "c.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        (comic / "ignored.txt").write_text("nope")

        result = FileManager.get_image_files(comic)
        names = [p.name for p in result]
        assert names == ["a.jpg", "b.jpg", "c.png"]

    def test_dedupes_case_insensitive_extensions(self, config_paths):
        comic = config_paths["comic"]
        (comic / "x.jpg").write_bytes(_jpg_bytes())
        (comic / "X.JPG").write_bytes(_jpg_bytes())
        result = FileManager.get_image_files(comic)
        # normcase + abspath 去重 → 只剩一个
        assert len(result) == 1

    def test_default_dir_is_config(self, config_paths):
        comic = config_paths["comic"]
        (comic / "z.jpg").write_bytes(_jpg_bytes())
        result = FileManager.get_image_files()  # 不传参
        assert any(p.name == "z.jpg" for p in result)


# ---------------- move_image ----------------

class TestMoveImage:
    def test_moves_to_target_dir(self, config_paths):
        comic = config_paths["comic"]
        target = config_paths["target"]
        src = comic / "src.jpg"
        src.write_bytes(_jpg_bytes())
        ok, msg, new_path = FileManager.move_image(src)
        assert ok is True
        assert new_path.parent == target
        assert not src.exists()
        assert new_path.exists()
        # 撤销栈有记录
        assert UndoManager.size() == 1
        rec = UndoManager.pop()
        assert rec["type"] == UndoOperationType.MOVE

    def test_target_exists_appends_counter(self, config_paths):
        comic = config_paths["comic"]
        target = config_paths["target"]
        src = comic / "dup.jpg"
        src.write_bytes(_jpg_bytes())
        (target / "dup.jpg").write_bytes(_jpg_bytes())

        ok, _, new_path = FileManager.move_image(src)
        assert ok is True
        assert new_path.name == "dup_1.jpg"

    def test_move_failure_returns_false(self, config_paths):
        src = config_paths["comic"] / "x.jpg"
        # 不创建文件，shutil.move 会抛
        ok, msg, new_path = FileManager.move_image(src)
        assert ok is False
        assert new_path is None


# ---------------- delete_image ----------------

class TestDeleteImage:
    def test_delegates_to_trash_and_records_undo(self, config_paths):
        comic = config_paths["comic"]
        trash = config_paths["trash"]
        src = comic / "to_del.jpg"
        src.write_bytes(_jpg_bytes())

        ok, _ = FileManager.delete_image(src)
        assert ok is True
        assert not src.exists()
        assert (trash / "to_del.jpg").exists()
        assert UndoManager.size() == 1
        rec = UndoManager.pop()
        assert rec["type"] == UndoOperationType.DELETE
        assert rec["data"]["name"] == "to_del"

    def test_source_missing_returns_false(self, config_paths):
        ok, msg = FileManager.delete_image(config_paths["comic"] / "ghost.jpg")
        assert ok is False


# ---------------- trash 委托 ----------------

class TestTrashDelegate:
    def test_get_trash_records(self, trash_records_path):
        write_json(trash_records_path, [{"name": "r1"}])
        recs = FileManager.get_trash_records()
        assert recs == [{"name": "r1"}]

    def test_restore_from_trash_delegates(self, config_paths, trash_records_path):
        trash = config_paths["trash"]
        (trash / "x.jpg").write_bytes(_jpg_bytes())
        write_json(trash_records_path, [
            {"name": "x", "extension": ".jpg", "original_path": "x.jpg",
             "deleted_time": "2026-01-01 00:00:00", "file_size": 100}
        ])
        ok, _ = FileManager.restore_from_trash("x")
        assert ok is True

    def test_permanent_delete_delegates(self, config_paths, trash_records_path):
        trash = config_paths["trash"]
        (trash / "y.jpg").write_bytes(_jpg_bytes())
        write_json(trash_records_path, [
            {"name": "y", "extension": ".jpg", "original_path": "y.jpg",
             "deleted_time": "2026-01-01 00:00:00", "file_size": 100}
        ])
        ok, _ = FileManager.permanent_delete("y")
        assert ok is True
        assert not (trash / "y.jpg").exists()

    def test_empty_trash_delegates(self, config_paths, trash_records_path):
        (config_paths["trash"] / "z.jpg").write_bytes(_jpg_bytes())
        write_json(trash_records_path, [{"name": "z"}])
        ok, _ = FileManager.empty_trash()
        assert ok is True


# ---------------- load/save_json_data ----------------

class TestJsonDataIO:
    def test_load_default_path(self, image_names_path):
        write_json(image_names_path, [{"name": "a"}])
        assert FileManager.load_json_data() == [{"name": "a"}]

    def test_load_explicit_path(self, tmp_path):
        p = tmp_path / "x.json"
        p.write_text(json.dumps([{"name": "b"}]), encoding="utf-8")
        assert FileManager.load_json_data(p) == [{"name": "b"}]

    def test_load_default_when_file_missing(self):
        assert FileManager.load_json_data() == []

    def test_save_default_path(self, image_names_path):
        assert FileManager.save_json_data([{"name": "c"}]) is True
        assert JsonStorage.load(image_names_path) == [{"name": "c"}]

    def test_save_explicit_path(self, tmp_path):
        p = tmp_path / "y.json"
        assert FileManager.save_json_data([{"name": "d"}], p) is True
        assert json.loads(p.read_text(encoding="utf-8")) == [{"name": "d"}]


# ---------------- extract_image_names_from_directory ----------------

class TestExtract:
    def test_source_not_exists(self, config_paths):
        result = FileManager.extract_image_names_from_directory(
            config_paths["comic"] / "ghost"
        )
        assert result["success"] is False
        assert "不存在" in result["message"]

    def test_source_is_file_not_dir(self, config_paths):
        f = config_paths["comic"] / "f.jpg"
        f.write_bytes(_jpg_bytes())
        result = FileManager.extract_image_names_from_directory(f)
        assert result["success"] is False
        assert "不是目录" in result["message"]

    def test_no_images_found(self, config_paths):
        d = config_paths["comic"] / "empty"
        d.mkdir()
        result = FileManager.extract_image_names_from_directory(d)
        assert result["success"] is False
        assert "未找到" in result["message"]

    def test_append_mode_writes_records_and_undo(
        self, config_paths, image_names_path
    ):
        d = config_paths["comic"] / "src"
        d.mkdir()
        for n in ["1.jpg", "2.jpg", "3.jpg"]:
            (d / n).write_bytes(_jpg_bytes())

        result = FileManager.extract_image_names_from_directory(
            d, append_mode=True
        )
        assert result["success"] is True
        assert result["added_count"] == 3
        assert result["total_count"] == 3
        # image_names.json 拿到 3 条
        assert len(JsonStorage.load(image_names_path)) == 3
        # 撤销栈多一条 EXTRACT
        rec = UndoManager.pop()
        assert rec["type"] == UndoOperationType.EXTRACT

    def test_overwrite_mode_clears_existing(
        self, config_paths, image_names_path
    ):
        write_json(image_names_path, [{"name": "old"}])
        d = config_paths["comic"] / "src"
        d.mkdir()
        (d / "new.jpg").write_bytes(_jpg_bytes())
        result = FileManager.extract_image_names_from_directory(
            d, append_mode=False
        )
        assert result["success"] is True
        assert result["total_count"] == 1
        assert JsonStorage.load(image_names_path)[0]["name"] == "new"

    def test_delete_after_extract_removes_source_files(
        self, config_paths, image_names_path
    ):
        d = config_paths["comic"] / "src"
        d.mkdir()
        for n in ["a.jpg", "b.jpg"]:
            (d / n).write_bytes(_jpg_bytes())

        result = FileManager.extract_image_names_from_directory(
            d, append_mode=True, delete_after_extract=True
        )
        assert result["success"] is True
        assert result["deleted_count"] == 2
        # 源文件已删
        assert not (d / "a.jpg").exists()
        assert not (d / "b.jpg").exists()
        # image_names.json 仍有 2 条
        assert len(JsonStorage.load(image_names_path)) == 2

    def test_delete_after_extract_with_save_failure_no_deletion(
        self, config_paths, image_names_path
    ):
        d = config_paths["comic"] / "src"
        d.mkdir()
        (d / "q.jpg").write_bytes(_jpg_bytes())
        with patch.object(JsonStorage, "save", return_value=False):
            result = FileManager.extract_image_names_from_directory(
                d, append_mode=True, delete_after_extract=True
            )
        assert result["success"] is False
        assert result["deleted_count"] == 0
        # 源文件应仍在
        assert (d / "q.jpg").exists()


# ---------------- get_stats ----------------

class TestGetStats:
    def test_stats_when_no_json(self, config_paths):
        stats = FileManager.get_stats()
        assert stats["file_exists"] is False
        assert stats["item_count"] == 0
        assert stats["json_path"].endswith("image_names.json")

    def test_stats_with_valid_json(self, image_names_path):
        write_json(image_names_path, sample_image_records(3, start=1))
        stats = FileManager.get_stats()
        assert stats["file_exists"] is True
        assert stats["item_count"] == 3
        assert stats["first_added"] == "2026-01-01 00:00:01"
        assert stats["last_added"] == "2026-01-01 00:00:03"
        assert "file_size_kb" in stats

    def test_stats_with_corrupted_json_does_not_raise(self, image_names_path):
        image_names_path.write_text("{ corrupted", encoding="utf-8")
        stats = FileManager.get_stats()
        # 内部 try/except 兜底
        assert stats["file_exists"] is True
        assert stats["item_count"] == 0
