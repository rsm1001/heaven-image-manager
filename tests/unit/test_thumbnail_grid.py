"""缩略图网格与单图预览联动测试。"""
import os
from pathlib import Path

from PIL import Image
from PyQt5.QtWidgets import QMessageBox, QStackedWidget

from core.file_management.file_manager import FileManager
from ui.preview_widget import PreviewWidget
from ui.thumbnail_grid import ThumbnailCache, ThumbnailGridWidget
from utils.config import Config


def _write_image(path: Path, color: str) -> None:
    Image.new("RGB", (320, 240), color).save(path)


def test_thumbnail_cache_uses_lru_eviction(qapp):
    """缓存达到容量时应淘汰最久未访问的项。"""
    from PyQt5.QtGui import QPixmap

    cache = ThumbnailCache(capacity=2)
    first, second, third = object(), object(), object()
    pixmap = QPixmap(1, 1)

    cache.put(first, pixmap)
    cache.put(second, pixmap)
    assert cache.get(first) is pixmap  # first becomes most recently used
    cache.put(third, pixmap)

    assert cache.get(second) is None
    assert cache.get(first) is pixmap
    assert cache.get(third) is pixmap


def test_thumbnail_grid_loads_visible_items_and_emits_path(qtbot, tmp_path):
    paths = []
    for index, color in enumerate(("red", "green", "blue")):
        path = tmp_path / "image_{}.png".format(index)
        _write_image(path, color)
        paths.append(path)

    grid = ThumbnailGridWidget()
    qtbot.addWidget(grid)
    grid.resize(600, 420)
    grid.set_images(paths, current_index=1)
    grid.show()

    qtbot.waitUntil(lambda: len(grid._cache) > 0, timeout=3000)
    assert grid.model.rowCount() == len(paths)
    assert grid.view.currentIndex().row() == 1

    received = []
    grid.image_activated.connect(received.append)
    grid._activate_index(grid.model.index(2, 0))
    assert received == [paths[2]]


def test_preview_thumbnail_click_returns_to_selected_single_image(qtbot):
    paths = []
    for index, color in enumerate(("red", "green", "blue")):
        path = Config.COMIC_DIR / "preview_{}.png".format(index)
        _write_image(path, color)
        paths.append(path)

    widget = PreviewWidget()
    qtbot.addWidget(widget)
    widget.resize(800, 600)
    widget.show()
    widget.load_images()

    widget.grid_button.setChecked(True)
    assert isinstance(widget.preview_stack, QStackedWidget)
    assert widget.preview_stack.currentWidget() is widget.thumbnail_grid
    assert widget.thumbnail_grid.model.rowCount() == len(paths)

    load_calls = []
    original_show_current_image = widget.show_current_image

    def counted_show_current_image():
        load_calls.append(True)
        original_show_current_image()

    widget.show_current_image = counted_show_current_image
    selected_path = widget.image_files[2]
    widget.open_image_from_thumbnail(selected_path)
    assert len(load_calls) == 1
    assert widget.current_index == 2
    assert not widget.grid_button.isChecked()
    assert widget.preview_stack.currentWidget() is widget.scroll_area


def test_idle_grid_does_not_reschedule_from_repaints(qtbot, tmp_path):
    path = tmp_path / "idle.png"
    _write_image(path, "purple")

    grid = ThumbnailGridWidget()
    qtbot.addWidget(grid)
    grid.resize(600, 420)
    grid.set_images([path])

    passes = []
    original_loader = grid._load_visible_thumbnails

    def counted_loader():
        passes.append(True)
        original_loader()

    grid._load_visible_thumbnails = counted_loader
    grid.show()
    qtbot.wait(300)

    # Show/resize/initial scheduling may require a few passes, but idle repaints
    # must not continuously enqueue new zero-delay work.
    assert len(passes) <= 4


def test_stale_thumbnail_result_preserves_active_pending_marker(qtbot):
    grid = ThumbnailGridWidget()
    qtbot.addWidget(grid)
    key = ("image", 1, 1)
    grid._generation = 2
    grid._pending_keys.add(key)

    # A result from generation 1 must not clear a request belonging to generation 2.
    grid._on_thumbnail_loaded(key, 1, b"invalid")
    assert key in grid._pending_keys
    grid._on_thumbnail_failed(key, 1, "stale failure")
    assert key in grid._pending_keys

    # The active generation is allowed to clear its own marker.
    grid._on_thumbnail_loaded(key, 2, b"invalid")
    assert key not in grid._pending_keys


def test_delete_last_image_clears_grid_and_controls(qtbot, monkeypatch):
    path = Config.COMIC_DIR / "last.png"
    _write_image(path, "red")

    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.Ok)
    monkeypatch.setattr(FileManager, "delete_image", lambda image_path: (True, "已删除"))

    widget = PreviewWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.load_images()
    widget.grid_button.setChecked(True)

    widget.delete_current_image()

    assert widget.image_files == []
    assert widget.thumbnail_grid.model.rowCount() == 0
    assert not widget.grid_button.isChecked()
    assert not widget.grid_button.isEnabled()
    assert widget.preview_stack.currentWidget() is widget.scroll_area


def test_visible_grid_recomputes_cache_key_for_in_place_replacement(qtbot, tmp_path):
    path = tmp_path / "replace.png"
    _write_image(path, "red")

    widget = PreviewWidget()
    qtbot.addWidget(widget)
    widget.resize(800, 600)
    widget.show()
    widget.image_files = [path]
    widget.current_index = 0
    widget.sync_thumbnail_grid(force=True)
    widget.grid_button.setChecked(True)

    old_key = widget.thumbnail_grid.model.item(0).data(widget.thumbnail_grid.KEY_ROLE)
    old_mtime_ns = path.stat().st_mtime_ns
    _write_image(path, "blue")
    os.utime(path, ns=(old_mtime_ns + 2_000_000_000, old_mtime_ns + 2_000_000_000))

    widget.thumbnail_grid._load_visible_thumbnails()

    new_key = widget.thumbnail_grid.model.item(0).data(widget.thumbnail_grid.KEY_ROLE)
    assert new_key != old_key


def test_scrolling_loads_thumbnails_from_newly_visible_rows(qtbot, tmp_path):
    paths = []
    for index in range(60):
        path = tmp_path / "scroll_{}.png".format(index)
        _write_image(path, "red")
        paths.append(path)

    grid = ThumbnailGridWidget()
    qtbot.addWidget(grid)
    grid.resize(600, 420)
    grid.set_images(paths)
    grid.show()
    qtbot.wait(700)

    last_key = grid.cache_key_for(paths[-1])
    assert last_key not in grid._cache._items

    scrollbar = grid.view.verticalScrollBar()
    scrollbar.setValue(scrollbar.maximum())
    qtbot.waitUntil(lambda: last_key in grid._cache._items, timeout=3000)


def test_keyboard_selection_updates_preview_index(qtbot):
    paths = []
    for index, color in enumerate(("red", "green", "blue")):
        path = Config.COMIC_DIR / "keyboard_{}.png".format(index)
        _write_image(path, color)
        paths.append(path)

    widget = PreviewWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.load_images()
    widget.grid_button.setChecked(True)

    widget.thumbnail_grid.view.setCurrentIndex(widget.thumbnail_grid.model.index(2, 0))

    assert widget.current_index == 2
    assert widget.delete_button.isEnabled()


def test_grid_navigation_does_not_decode_hidden_single_image(qtbot, monkeypatch):
    for index, color in enumerate(("red", "green", "blue")):
        _write_image(Config.COMIC_DIR / "grid_nav_{}.png".format(index), color)

    widget = PreviewWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.load_images()
    widget.grid_button.setChecked(True)

    load_calls = []

    def unexpected_full_image_load(image_path):
        load_calls.append(image_path)
        return None

    monkeypatch.setattr("ui.preview_widget.ImageProcessor.load_and_resize_image", unexpected_full_image_load)
    widget.show_next_image()
    widget.resize(900, 650)

    assert load_calls == []
    assert widget.current_index == 1


def test_delete_non_final_image_keeps_grid_aligned_with_file_list(qtbot, monkeypatch):
    paths = []
    for index, color in enumerate(("red", "green", "blue")):
        path = Config.COMIC_DIR / "delete_grid_{}.png".format(index)
        _write_image(path, color)
        paths.append(path)

    deleted = []

    def fake_delete(image_path):
        deleted.append(image_path)
        return True, "???"

    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.Ok)
    monkeypatch.setattr(FileManager, "delete_image", fake_delete)

    widget = PreviewWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.load_images()
    widget.grid_button.setChecked(True)

    widget.delete_current_image()

    assert deleted == [paths[0]]
    assert widget.image_files == paths[1:]
    assert widget.thumbnail_grid.model.rowCount() == 2
    model_paths = [
        Path(widget.thumbnail_grid.model.item(row).data(widget.thumbnail_grid.PATH_ROLE))
        for row in range(widget.thumbnail_grid.model.rowCount())
    ]
    assert model_paths == widget.image_files
    selected_row = widget.thumbnail_grid.view.currentIndex().row()
    assert selected_row == widget.current_index
    assert model_paths[selected_row] == widget.image_files[widget.current_index]

    # The next delete must target the file represented by the selected thumbnail.
    widget.delete_current_image()
    assert deleted == [paths[0], paths[2]]


def test_undo_replaced_image_list_resynchronizes_visible_grid(qtbot, tmp_path):
    paths = []
    for index, color in enumerate(("red", "green", "blue")):
        path = tmp_path / "undo_grid_{}.png".format(index)
        _write_image(path, color)
        paths.append(path)

    widget = PreviewWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.image_files = paths[:2]
    widget.current_index = 0
    widget.sync_thumbnail_grid(force=True)
    widget.grid_button.setChecked(True)

    # ?? MainWindow.on_undo() ???? image_files ??? show_current_image?
    widget.image_files = paths
    widget.current_index = 2
    widget.show_current_image()

    model_paths = [
        Path(widget.thumbnail_grid.model.item(row).data(widget.thumbnail_grid.PATH_ROLE))
        for row in range(widget.thumbnail_grid.model.rowCount())
    ]
    assert model_paths == paths
    assert widget.thumbnail_grid.view.currentIndex().row() == 2
    assert widget.current_index == 2


def test_move_last_image_clears_grid_and_controls(qtbot, monkeypatch):
    path = Config.COMIC_DIR / "move_last.png"
    _write_image(path, "red")

    monkeypatch.setattr(FileManager, "move_image", lambda image_path: (
        True, "???", Config.TARGET_DIR / image_path.name
    ))
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.Ok)

    widget = PreviewWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget.load_images()
    widget.grid_button.setChecked(True)

    widget.move_current_image()

    assert widget.image_files == []
    assert widget.current_index == -1
    assert widget.thumbnail_grid.model.rowCount() == 0
    assert not widget.grid_button.isChecked()
    assert not widget.grid_button.isEnabled()
    assert widget.preview_stack.currentWidget() is widget.scroll_area
    assert widget.counter_label.text() == "0/0"
