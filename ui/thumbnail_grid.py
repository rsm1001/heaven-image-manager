"""延迟加载的缩略图网格。"""
from collections import OrderedDict
from io import BytesIO
from pathlib import Path
from typing import Iterable, Optional, Tuple

from PIL import Image, ImageOps
from PyQt5.QtCore import (
    QEvent,
    QModelIndex,
    QItemSelectionModel,
    QObject,
    QPoint,
    QRunnable,
    QSize,
    Qt,
    QThreadPool,
    QTimer,
    pyqtSignal,
    pyqtSlot,
)
from PyQt5.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt5.QtWidgets import QAbstractItemView, QListView, QVBoxLayout, QWidget
from PyQt5.QtGui import QStandardItem, QStandardItemModel

from utils.logger import logger


class ThumbnailCache:
    """主线程使用的有界 LRU 缩略图缓存。"""

    def __init__(self, capacity: int = 512):
        self.capacity = max(1, int(capacity))
        self._items = OrderedDict()

    def get(self, key):
        pixmap = self._items.pop(key, None)
        if pixmap is not None:
            self._items[key] = pixmap
        return pixmap

    def put(self, key, pixmap: QPixmap) -> None:
        self._items.pop(key, None)
        self._items[key] = pixmap
        while len(self._items) > self.capacity:
            self._items.popitem(last=False)

    def clear(self) -> None:
        self._items.clear()

    def __len__(self) -> int:
        return len(self._items)


class ThumbnailLoadSignals(QObject):
    """QRunnable 与界面线程之间的结果信号。"""

    loaded = pyqtSignal(object, int, bytes)
    failed = pyqtSignal(object, int, str)


class ThumbnailLoadTask(QRunnable):
    """后台解码并生成 PNG 缩略图字节，绝不在工作线程创建 QPixmap。"""

    def __init__(self, image_path: Path, cache_key, generation: int, thumbnail_size: QSize):
        super().__init__()
        self.image_path = image_path
        self.cache_key = cache_key
        self.generation = generation
        self.thumbnail_size = thumbnail_size
        self.signals = ThumbnailLoadSignals()
        self.setAutoDelete(True)

    @pyqtSlot()
    def run(self) -> None:
        try:
            with Image.open(self.image_path) as source:
                image = ImageOps.exif_transpose(source)
                resampling = getattr(Image, "Resampling", Image).LANCZOS
                image.thumbnail(
                    (self.thumbnail_size.width(), self.thumbnail_size.height()),
                    resampling,
                )
                if image.mode not in ("RGB", "RGBA"):
                    image = image.convert("RGBA" if "transparency" in image.info else "RGB")

                output = BytesIO()
                image.save(output, format="PNG", optimize=True)

            self.signals.loaded.emit(self.cache_key, self.generation, output.getvalue())
        except Exception as exc:  # 损坏/不支持的文件不能阻塞整个网格。
            self.signals.failed.emit(self.cache_key, self.generation, str(exc))


class ThumbnailGridWidget(QWidget):
    """QListView IconMode 缩略图网格，只请求可见区域及少量预读项。"""

    PATH_ROLE = Qt.UserRole + 1
    KEY_ROLE = Qt.UserRole + 2
    APPLIED_ICON_ROLE = Qt.UserRole + 3

    image_activated = pyqtSignal(Path)
    selection_changed = pyqtSignal(int)

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        thumbnail_size: QSize = QSize(160, 160),
        cache_capacity: int = 512,
    ):
        super().__init__(parent)
        self.thumbnail_size = thumbnail_size
        self.grid_size = QSize(thumbnail_size.width() + 18, thumbnail_size.height() + 42)
        self._generation = 0
        self._pending_keys = set()
        self._failed_keys = set()
        self._row_by_key = {}
        self._visible_load_scheduled = False
        self._cache = ThumbnailCache(cache_capacity)
        self._thread_pool = QThreadPool(self)
        self._thread_pool.setMaxThreadCount(max(1, min(4, QThreadPool.globalInstance().maxThreadCount())))

        self.view = QListView(self)
        self.model = QStandardItemModel(self)
        self.view.setModel(self.model)
        self.view.setViewMode(QListView.IconMode)
        self.view.setFlow(QListView.LeftToRight)
        self.view.setWrapping(True)
        self.view.setResizeMode(QListView.Adjust)
        self.view.setLayoutMode(QListView.Batched)
        self.view.setBatchSize(100)
        self.view.setMovement(QListView.Static)
        self.view.setUniformItemSizes(True)
        self.view.setIconSize(self.thumbnail_size)
        self.view.setGridSize(self.grid_size)
        self.view.setWordWrap(False)
        self.view.setTextElideMode(Qt.ElideMiddle)
        self.view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.view.setSpacing(6)
        self.view.setObjectName("thumbnailGridView")
        self.view.setToolTip("单击缩略图进入单图预览")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)

        self._placeholder_icon = self._create_status_icon("加载中", "#4A4A4A", "#BDBDBD")
        self._error_icon = self._create_status_icon("无法预览", "#5A3030", "#F0B4B4")
        self.view.clicked.connect(self._activate_index)
        self.view.activated.connect(self._activate_index)
        self.view.selectionModel().currentChanged.connect(self._on_current_changed)
        self.view.verticalScrollBar().valueChanged.connect(self.schedule_visible_load)
        self.view.viewport().installEventFilter(self)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self.view.viewport() and event.type() in (QEvent.Resize, QEvent.Show):
            self.schedule_visible_load()
        return super().eventFilter(watched, event)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.schedule_visible_load()

    def set_images(self, image_files: Iterable[Path], current_index: int = -1) -> None:
        """以轻量模型一次性登记路径；真正的图像解码延迟到进入可见区。"""
        self._generation += 1
        self._pending_keys.clear()
        self._failed_keys.clear()
        self._row_by_key.clear()
        self.model.clear()

        for image_path in image_files:
            item = QStandardItem(self._placeholder_icon, image_path.name)
            item.setEditable(False)
            item.setToolTip(str(image_path))
            cache_key = self.cache_key_for(image_path)
            item.setData(str(image_path), self.PATH_ROLE)
            item.setData(cache_key, self.KEY_ROLE)
            self._row_by_key[cache_key] = self.model.rowCount()
            self.model.appendRow(item)

        self.set_current_index(current_index, ensure_visible=False)
        self.schedule_visible_load()

    def set_current_index(self, current_index: int, ensure_visible: bool = True) -> None:
        if not 0 <= current_index < self.model.rowCount():
            self.view.clearSelection()
            self.view.setCurrentIndex(QModelIndex())
            return

        index = self.model.index(current_index, 0)
        self.view.setCurrentIndex(index)
        self.view.selectionModel().select(index, QItemSelectionModel.ClearAndSelect)
        if ensure_visible:
            self.view.scrollTo(index, QAbstractItemView.PositionAtCenter)
        self.schedule_visible_load()

    @staticmethod
    def cache_key_for(image_path: Path) -> Tuple[str, int, int]:
        """文件路径、修改时间和大小共同决定缓存版本，修改文件后自然失效。"""
        try:
            stat = image_path.stat()
            return (str(image_path.resolve()), stat.st_mtime_ns, stat.st_size)
        except OSError:
            return (str(image_path.absolute()), -1, -1)

    def schedule_visible_load(self, *args) -> None:
        """合并高频滚动、重绘和尺寸变化事件，下一轮事件循环只计算一次。"""
        if self._visible_load_scheduled:
            return
        self._visible_load_scheduled = True
        QTimer.singleShot(0, self._load_visible_thumbnails)

    def _load_visible_thumbnails(self) -> None:
        self._visible_load_scheduled = False
        if not self.isVisible() or self.model.rowCount() == 0:
            return

        viewport = self.view.viewport()
        if viewport.width() <= 0 or viewport.height() <= 0:
            return

        # 不要直接探测 QListView 的边角，间距可能萱在空隙中。
        # 使用网格单元的水平中心，并沿垂直方向向可见区域内部探测。
        # 确保 indexAt() 命中 item，而不是 spacing。
        first = self._row_near_viewport_edge(0, search_down=True)
        last = self._row_near_viewport_edge(viewport.height() - 1, search_down=False)

        columns = max(1, viewport.width() // max(1, self.grid_size.width()))
        if first < 0:
            # 极端情况下无法命中 item 时，根据滚动偏移估算当前行，
            # 不能固定回退到第 0 行，否则滚动后只会继续加载首屏。
            estimated_row = self.view.verticalScrollBar().value() // max(1, self.grid_size.height())
            first = min(self.model.rowCount() - 1, max(0, estimated_row * columns))
        if last < 0:
            visible_rows = max(1, viewport.height() // max(1, self.grid_size.height()) + 1)
            last = min(self.model.rowCount() - 1, first + columns * visible_rows - 1)

        prefetch = columns * 2
        start = max(0, first - prefetch)
        end = min(self.model.rowCount() - 1, last + prefetch)
        for row in range(start, end + 1):
            self._request_thumbnail(row)

    def _row_near_viewport_edge(self, y: int, search_down: bool) -> int:
        """从视口边缘向内部探测 item 行，避开 QListView 的空白间隔。"""
        viewport = self.view.viewport()
        width = viewport.width()
        height = viewport.height()
        if width <= 0 or height <= 0:
            return -1

        cell_width = max(1, self.grid_size.width())
        cell_height = max(1, self.grid_size.height())
        column_count = max(1, (width + cell_width - 1) // cell_width)
        x_positions = [
            min(width - 1, cell_width // 2 + column * cell_width)
            for column in range(column_count)
        ]
        # 额外探测视口中心，兼容 QListView 在部分宽度下的对齐变化。
        x_positions.append(width // 2)

        y = max(0, min(height - 1, y))
        max_offset = min(height - 1, cell_height)
        for offset in range(0, max_offset + 1, 4):
            candidate_y = y + offset if search_down else y - offset
            if candidate_y < 0 or candidate_y >= height:
                continue
            for candidate_x in x_positions:
                index = self.view.indexAt(QPoint(candidate_x, candidate_y))
                if index.isValid():
                    return index.row()
        return -1

    def _request_thumbnail(self, row: int) -> None:
        item = self.model.item(row)
        if item is None:
            return

        image_path = Path(item.data(self.PATH_ROLE))
        stored_key = item.data(self.KEY_ROLE)
        cache_key = self.cache_key_for(image_path)
        if cache_key != stored_key:
            # 只为当前可见或预读条目重算文件元数据，避免滚动或翻页时扫描整份列表。
            if self._row_by_key.get(stored_key) == row:
                self._row_by_key.pop(stored_key, None)
            self._row_by_key[cache_key] = row
            self._failed_keys.discard(stored_key)
            item.setData(cache_key, self.KEY_ROLE)
            item.setData(None, self.APPLIED_ICON_ROLE)
            item.setIcon(self._placeholder_icon)

        cached = self._cache.get(cache_key)
        if cached is not None:
            if item.data(self.APPLIED_ICON_ROLE) != cache_key:
                item.setIcon(QIcon(cached))
                item.setData(cache_key, self.APPLIED_ICON_ROLE)
            return
        if cache_key in self._pending_keys or cache_key in self._failed_keys:
            return

        self._pending_keys.add(cache_key)
        task = ThumbnailLoadTask(image_path, cache_key, self._generation, self.thumbnail_size)
        task.signals.loaded.connect(self._on_thumbnail_loaded)
        task.signals.failed.connect(self._on_thumbnail_failed)
        self._thread_pool.start(task)

    @pyqtSlot(object, int, bytes)
    def _on_thumbnail_loaded(self, cache_key, generation: int, image_bytes: bytes) -> None:
        if generation != self._generation:
            return
        self._pending_keys.discard(cache_key)

        pixmap = QPixmap()
        if not pixmap.loadFromData(image_bytes, "PNG"):
            logger.warning("缩略图数据无法转换为 QPixmap")
            return

        self._cache.put(cache_key, pixmap)
        row = self._row_by_key.get(cache_key)
        item = self.model.item(row) if row is not None else None
        if item is not None and item.data(self.KEY_ROLE) == cache_key:
            item.setIcon(QIcon(pixmap))
            item.setData(cache_key, self.APPLIED_ICON_ROLE)

    @pyqtSlot(object, int, str)
    def _on_thumbnail_failed(self, cache_key, generation: int, message: str) -> None:
        if generation != self._generation:
            return
        self._pending_keys.discard(cache_key)
        if generation == self._generation:
            self._failed_keys.add(cache_key)
            row = self._row_by_key.get(cache_key)
            item = self.model.item(row) if row is not None else None
            if item is not None and item.data(self.KEY_ROLE) == cache_key:
                item.setIcon(self._error_icon)
                item.setData(cache_key, self.APPLIED_ICON_ROLE)
            logger.warning("加载缩略图失败: %s", message)

    @pyqtSlot(QModelIndex, QModelIndex)
    def _on_current_changed(self, current: QModelIndex, previous: QModelIndex) -> None:
        if current.isValid():
            self.selection_changed.emit(current.row())

    @pyqtSlot(QModelIndex)
    def _activate_index(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        value = index.data(self.PATH_ROLE)
        if value:
            self.image_activated.emit(Path(value))

    def _create_status_icon(self, text: str, background: str, foreground: str) -> QIcon:
        """创建加载中或不可预览状态图标，避免失败文件持续显示为加载中。"""
        pixmap = QPixmap(self.thumbnail_size)
        pixmap.fill(QColor(background))
        painter = QPainter(pixmap)
        painter.setPen(QColor(foreground))
        painter.drawText(pixmap.rect(), Qt.AlignCenter, text)
        painter.end()
        return QIcon(pixmap)
