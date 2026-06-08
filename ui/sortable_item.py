"""类型感知的 QTableWidgetItem

为 QTableWidget 提供按"原始数据类型"排序的能力。
默认 QTableWidgetItem 在开启 setSortingEnabled 时只能按显示文本字典序比较,
对"1.5 KB / 10.0 KB / 2.0 MB"之类的列会排错,本类解决这类问题。

使用方法:在创建单元格时指定 sort_kind 即可,其余 API 与 QTableWidgetItem 一致。

    from ui.sortable_item import SortableTableItem
    cell = SortableTableItem("1.5 KB", sort_kind="filesize")
    table.setItem(row, col, cell)

sort_kind 支持: "str" / "int" / "float" / "datetime" / "filesize"
解析失败时回退到字符串比较,保证单行异常不会影响整张表。
"""
from functools import total_ordering
from datetime import datetime
import re
from typing import Any

from PyQt5.QtWidgets import QTableWidgetItem


@total_ordering
class SortableTableItem(QTableWidgetItem):
    """按指定类型比较的 QTableWidgetItem"""

    _SIZE_PATTERN = re.compile(r'^\s*([\d.]+)\s*(B|KB|MB|GB|K|M|G)?\s*$', re.IGNORECASE)

    _DATETIME_FORMATS = (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    )

    def __init__(self, text: str = "", sort_kind: str = "str",
                 sort_value: Any = None):
        super().__init__(text)
        self._sort_kind = sort_kind
        if sort_value is not None:
            self._sort_value = sort_value
        else:
            self._sort_value = self._parse_value(text)

    def _parse_value(self, text: str) -> Any:
        if text is None:
            text = ""
        kind = self._sort_kind
        if kind == "str":
            return str(text).lower()
        if kind == "int":
            try:
                return int(str(text).strip())
            except (ValueError, TypeError):
                return 0
        if kind == "float":
            try:
                return float(str(text).strip())
            except (ValueError, TypeError):
                return 0.0
        if kind == "datetime":
            return self._parse_datetime(str(text))
        if kind == "filesize":
            return self._parse_size(str(text))
        return str(text).lower()

    @staticmethod
    def _parse_datetime(text: str) -> Any:
        text = (text or "").strip()
        if not text:
            return ""
        for fmt in SortableTableItem._DATETIME_FORMATS:
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
        return text

    @staticmethod
    def _parse_size(text: str) -> int:
        match = SortableTableItem._SIZE_PATTERN.match(text or "")
        if not match:
            return 0
        value = float(match.group(1))
        unit = (match.group(2) or "B").upper()
        if unit.startswith("K"):
            value *= 1024
        elif unit.startswith("M"):
            value *= 1024 * 1024
        elif unit.startswith("G"):
            value *= 1024 * 1024 * 1024
        return int(value)

    def __lt__(self, other: "QTableWidgetItem") -> bool:
        if isinstance(other, SortableTableItem):
            if self._sort_kind == other._sort_kind:
                try:
                    return self._sort_value < other._sort_value
                except TypeError:
                    pass
        return self.text() < other.text()

    def __eq__(self, other) -> bool:
        if isinstance(other, SortableTableItem):
            if self._sort_kind == other._sort_kind:
                try:
                    return self._sort_value == other._sort_value
                except TypeError:
                    pass
        return self.text() == other.text()
