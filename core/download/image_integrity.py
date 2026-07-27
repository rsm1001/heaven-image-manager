"""图片完整性校验与 .part 临时文件清理。

提供魔数快速校验、临时文件清理、原子替换等工具函数。
对调用方无副作用；可被下载器、垃圾箱管理、批量校验等模块复用。
"""
from pathlib import Path

# 常见图片魔数（前 4–8 字节）
_IMAGE_MAGIC_BYTES = (
    b"\xff\xd8\xff",                # JPEG
    b"\x89PNG\r\n\x1a\n",            # PNG
    b"GIF87a",                       # GIF87a
    b"GIF89a",                       # GIF89a
    b"BM",                           # BMP
    b"RIFF",                         # WebP（RIFF 容器，前 4 字节是 RIFF）
)


def looks_like_image(path: Path, min_size: int) -> bool:
    """快速校验：文件存在 + 大小超阈值 + 头部字节匹配已知图片格式。"""
    try:
        if not path.exists():
            return False
        size = path.stat().st_size
        if size < min_size:
            return False
        with open(path, "rb") as f:
            head = f.read(8)
        if not head:
            return False
        # WebP: "RIFF????WEBP" → 头部前 4 字节 RIFF + 后续 "WEBP"
        if head.startswith(b"RIFF") and size >= 12:
            with open(path, "rb") as f:
                f.seek(8)
                tail_head = f.read(4)
            if tail_head == b"WEBP":
                return True
        return any(head.startswith(magic) for magic in _IMAGE_MAGIC_BYTES)
    except OSError:
        return False


def safe_unlink(path: Path) -> None:
    """best-effort 删文件，失败也不抛。"""
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass


def cleanup_stale_tmp_files(directory: Path, min_size: int = 0) -> int:
    """启动时清理上次未完成的 .part 文件（best-effort），返回清理数量。"""
    cleaned = 0
    try:
        for p in directory.glob("*.jpg.part"):
            try:
                if p.exists():
                    p.unlink()
                    cleaned += 1
            except OSError:
                continue
    except OSError:
        return cleaned
    return cleaned


def atomic_replace(tmp_path: Path, target_path: Path) -> bool:
    """将临时文件原子替换为目标文件；替换前清理可能存在的同名目标。

    失败时不会留下半截文件。
    """
    try:
        if target_path.exists():
            safe_unlink(target_path)
        tmp_path.replace(target_path)
        return True
    except OSError:
        safe_unlink(tmp_path)
        return False
