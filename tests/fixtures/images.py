"""PIL 图像 fixture 工厂：生成 1×1 PNG/JPG 字节流与磁盘文件。

提供：
- png_bytes() / jpg_bytes()：返回原始字节
- valid_png(tmp_path) / valid_jpg(tmp_path)：磁盘上的 1×1 合法图
- tiny_jpg(tmp_path)：< 1 KB，触发 ERROR_SIZE_MISMATCH
- truncated_jpg(tmp_path)：末尾截断，触发 ERROR_TRUNCATED
- broken_header_png(tmp_path)：写入 "not a png" 字节，触发 verify 失败
"""
import io
from pathlib import Path

import pytest
from PIL import Image


def _make_image(fmt: str, size=(1, 1), color=(255, 0, 0)) -> bytes:
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def png_bytes() -> bytes:
    return _make_image("PNG")


def jpg_bytes() -> bytes:
    return _make_image("JPEG")


@pytest.fixture
def valid_png(tmp_path: Path) -> Path:
    p = tmp_path / "a.png"
    p.write_bytes(png_bytes())
    return p


@pytest.fixture
def valid_jpg(tmp_path: Path) -> Path:
    p = tmp_path / "a.jpg"
    p.write_bytes(jpg_bytes())
    return p


@pytest.fixture
def tiny_jpg(tmp_path: Path) -> Path:
    """< 1024 字节，触发 ImageValidator 的 ERROR_SIZE_MISMATCH。"""
    p = tmp_path / "tiny.jpg"
    # JPEG header + 1 byte payload，远小于 1024
    p.write_bytes(b"\xff\xd8\xff\xe0\x00")
    return p


@pytest.fixture
def truncated_jpg(tmp_path: Path) -> Path:
    """末尾截断的 jpg，触发 ERROR_TRUNCATED。"""
    raw = jpg_bytes()
    # 砍掉最后 8 字节，保留头部让 verify 通过但 decode 失败
    p = tmp_path / "trunc.jpg"
    p.write_bytes(raw[: max(1, len(raw) - 8)])
    return p


@pytest.fixture
def broken_header_png(tmp_path: Path) -> Path:
    """非 PNG 字节，触发 verify 异常。"""
    p = tmp_path / "broken.png"
    p.write_bytes(b"this is not a png file at all, just plain text")
    # 把大小撑到 >= 1024，避免先撞上 size_mismatch 分支
    p.write_bytes(b"this is not a png file at all, just plain text" + b"\x00" * 1500)
    return p
