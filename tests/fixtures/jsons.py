"""JSON fixture 工厂：生成 image_names / trash_records / download_records 样例数据。

提供：
- sample_image_records(n, prefix)：image_names.json 用的 list
- sample_trash_records(n, prefix)：trash_records.json 用的 list
- write_json(path, data)：utf-8, ensure_ascii=False, indent=2 落盘
- populate_comic_dir(...)：在 Config.COMIC_DIR 下生成 n 张 1×1 jpg + image_names.json
"""
import io
import json
from pathlib import Path

import pytest
from PIL import Image


def sample_image_records(n: int = 3, prefix: str = "9", start: int = 0) -> list:
    """生成 [{name, source, extension, added_time}, ...] 结构。"""
    items = []
    for i in range(n):
        idx = start + i
        items.append(
            {
                "name": f"{prefix}{idx:03d}",
                "source": "comic\\101",
                "extension": ".jpg",
                "added_time": f"2026-01-01 00:00:{idx:02d}",
            }
        )
    return items


def sample_trash_records(n: int = 3, prefix: str = "x", start: int = 0) -> list:
    """生成 [{name, extension, original_path, deleted_time, file_size}, ...] 结构。"""
    items = []
    for i in range(n):
        idx = start + i
        items.append(
            {
                "name": f"{prefix}{idx}",
                "extension": ".jpg",
                "original_path": f"{prefix}{idx}.jpg",
                "deleted_time": f"2026-01-01 00:00:{idx:02d}",
                "file_size": 1024,
            }
        )
    return items


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _make_jpg_bytes() -> bytes:
    img = Image.new("RGB", (1, 1), (255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def populate_comic_dir(config_paths, image_names_path):
    """在 Config.COMIC_DIR 下生成 n 张 1×1 jpg + image_names.json。

    返回 (image_names_path, [jpg_path, ...])。
    """
    comic = config_paths["comic"]
    comic.mkdir(parents=True, exist_ok=True)

    def _populate(n: int = 3, start_id: int = 9001) -> tuple:
        paths = []
        records = []
        for i in range(n):
            jpg_path = comic / f"{start_id + i}.jpg"
            jpg_path.write_bytes(_make_jpg_bytes())
            paths.append(jpg_path)
            records.append(
                {
                    "name": str(start_id + i),
                    "source": "comic",
                    "extension": ".jpg",
                    "added_time": f"2026-01-01 00:00:{i:02d}",
                }
            )
        write_json(image_names_path, records)
        return image_names_path, paths

    return _populate
