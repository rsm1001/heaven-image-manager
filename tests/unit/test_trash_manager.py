"""core.trash_manager.TrashManager 单元测试。"""
import io
from pathlib import Path

import pytest
from PIL import Image

from core.trash_manager import TrashManager
from tests.fixtures.jsons import write_json, sample_trash_records


def _jpg_bytes() -> bytes:
    img = Image.new("RGB", (1, 1), (255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


# ---------------- add_to_trash ----------------

class TestAddToTrash:
    def test_moves_file_to_trash_dir(self, config_paths, trash_records_path):
        comic = config_paths["comic"]
        trash = config_paths["trash"]
        src = comic / "abc.jpg"
        src.write_bytes(_jpg_bytes())

        ok, msg = TrashManager.add_to_trash(src)
        assert ok is True
        assert "已移入垃圾桶" in msg
        assert not src.exists()
        assert (trash / "abc.jpg").exists()
        records = TrashManager._load_records()
        assert len(records) == 1
        assert records[0]["name"] == "abc"
        assert records[0]["extension"] == ".jpg"
        assert "deleted_time" in records[0]
        assert records[0]["file_size"] > 0

    def test_same_name_collision_appends_counter(self, config_paths, trash_records_path):
        comic = config_paths["comic"]
        trash = config_paths["trash"]
        # 提前放一个同名文件进 trash
        (trash / "abc.jpg").write_bytes(_jpg_bytes())

        src = comic / "abc.jpg"
        src.write_bytes(_jpg_bytes())
        ok, _ = TrashManager.add_to_trash(src)
        assert ok is True
        # 落到 abc_1.jpg
        assert (trash / "abc_1.jpg").exists()

    def test_source_not_exists_returns_failure(self, config_paths):
        ok, msg = TrashManager.add_to_trash(config_paths["comic"] / "nope.jpg")
        assert ok is False
        assert "失败" in msg

    def test_max_count_triggers_eviction(
        self, config_paths, trash_records_path, monkeypatch
    ):
        from utils import config as config_mod

        monkeypatch.setattr(config_mod.Config, "MAX_TRASH_COUNT", 2)
        comic = config_paths["comic"]
        trash = config_paths["trash"]
        # 第 1 张
        f1 = comic / "a.jpg"
        f1.write_bytes(_jpg_bytes())
        TrashManager.add_to_trash(f1)
        # 第 2 张
        f2 = comic / "b.jpg"
        f2.write_bytes(_jpg_bytes())
        TrashManager.add_to_trash(f2)
        # 第 3 张触发淘汰
        f3 = comic / "c.jpg"
        f3.write_bytes(_jpg_bytes())
        TrashManager.add_to_trash(f3)
        # records 限到 2
        records = TrashManager._load_records()
        assert len(records) == 2
        assert {r["name"] for r in records} == {"b", "c"}
        # 最久的 a.jpg 物理文件应被删
        assert not (trash / "a.jpg").exists()


# ---------------- get_all_records ----------------

class TestGetAllRecords:
    def test_empty(self, trash_records_path):
        assert TrashManager.get_all_records() == []

    def test_returns_records(self, trash_records_path):
        write_json(trash_records_path, sample_trash_records(3))
        recs = TrashManager.get_all_records()
        assert len(recs) == 3
        assert recs[0]["name"] == "x0"


# ---------------- restore ----------------

class TestRestore:
    def test_restore_no_record(self, config_paths, trash_records_path):
        ok, msg = TrashManager.restore("ghost")
        assert ok is False
        assert "记录不存在" in msg

    def test_restore_no_file(self, config_paths, trash_records_path):
        write_json(trash_records_path, sample_trash_records(1, prefix="ghost"))
        ok, msg = TrashManager.restore("ghost0")
        assert ok is False
        assert "找不到文件" in msg

    def test_restore_happy_path(self, config_paths, trash_records_path):
        comic = config_paths["comic"]
        trash = config_paths["trash"]
        name = "happy"
        (trash / f"{name}.jpg").write_bytes(_jpg_bytes())
        write_json(trash_records_path, [
            {"name": name, "extension": ".jpg", "original_path": f"{name}.jpg",
             "deleted_time": "2026-01-01 00:00:00", "file_size": 100}
        ])
        ok, msg = TrashManager.restore(name)
        assert ok is True
        assert (comic / f"{name}.jpg").exists()
        assert TrashManager._load_records() == []

    def test_restore_target_exists_appends_counter(
        self, config_paths, trash_records_path
    ):
        comic = config_paths["comic"]
        trash = config_paths["trash"]
        name = "dup"
        (comic / f"{name}.jpg").write_bytes(_jpg_bytes())
        (trash / f"{name}.jpg").write_bytes(_jpg_bytes())
        write_json(trash_records_path, [
            {"name": name, "extension": ".jpg", "original_path": f"{name}.jpg",
             "deleted_time": "2026-01-01 00:00:00", "file_size": 100}
        ])
        ok, _ = TrashManager.restore(name)
        assert ok is True
        # 落到 dup_1.jpg
        assert (comic / f"{name}_1.jpg").exists()


# ---------------- permanent_delete ----------------

class TestPermanentDelete:
    def test_no_record(self, trash_records_path):
        ok, msg = TrashManager.permanent_delete("nope")
        assert ok is False
        assert "记录不存在" in msg

    def test_deletes_file_and_record(
        self, config_paths, trash_records_path
    ):
        trash = config_paths["trash"]
        name = "perm"
        (trash / f"{name}.jpg").write_bytes(_jpg_bytes())
        write_json(trash_records_path, [
            {"name": name, "extension": ".jpg", "original_path": f"{name}.jpg",
             "deleted_time": "2026-01-01 00:00:00", "file_size": 100}
        ])
        ok, msg = TrashManager.permanent_delete(name)
        assert ok is True
        assert "已永久删除" in msg
        assert not (trash / f"{name}.jpg").exists()
        assert TrashManager._load_records() == []


# ---------------- empty ----------------

class TestEmpty:
    def test_empty_no_records(self, trash_records_path):
        ok, msg = TrashManager.empty()
        assert ok is True
        assert "已清空" in msg

    def test_empty_with_records(self, config_paths, trash_records_path):
        trash = config_paths["trash"]
        # sample_trash_records(3) 生成 name=x0, x1, x2
        for n in ["x0", "x1", "x2"]:
            (trash / f"{n}.jpg").write_bytes(_jpg_bytes())
        write_json(trash_records_path, sample_trash_records(3))
        ok, _ = TrashManager.empty()
        assert ok is True
        # 所有记录文件 unlink
        for n in ["x0", "x1", "x2"]:
            assert not (trash / f"{n}.jpg").exists()
        assert TrashManager._load_records() == []