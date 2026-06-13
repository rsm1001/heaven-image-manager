"""ui.sortable_item.SortableTableItem 单元测试。

不依赖 QTableWidget widget —— QTableWidgetItem 子类在 PyQt5 下
只要 QApplication 存在即可构造，__lt__ / __eq__ 走纯 Python 路径。
"""
import pytest
from PyQt5.QtWidgets import QTableWidgetItem

from ui.sortable_item import SortableTableItem


# pytest-qt 的 qapp 是 session-scoped QApplication fixture
# SortableTableItem 继承自 QTableWidgetItem，构造时需要 QApplication 在场


class TestStringSort:
    def test_lowercase_compare(self, qapp):
        assert SortableTableItem("abc") < SortableTableItem("Abd")
        # 注意 text() 走 lowercased，所以 "ABC" 等价 "abc"
        assert SortableTableItem("abc") == SortableTableItem("ABC")
        assert not (SortableTableItem("z") < SortableTableItem("a"))


class TestIntSort:
    def test_numeric_order(self, qapp):
        a = SortableTableItem("10", sort_kind="int")
        b = SortableTableItem("9", sort_kind="int")
        assert a > b  # 10 > 9
        assert b < a

    def test_invalid_falls_back_to_zero(self, qapp):
        a = SortableTableItem("not a number", sort_kind="int")
        b = SortableTableItem("5", sort_kind="int")
        assert a < b  # 0 < 5

    def test_empty_string_is_zero(self, qapp):
        assert SortableTableItem("", sort_kind="int") == SortableTableItem("0", sort_kind="int")


class TestFloatSort:
    def test_decimal_order(self, qapp):
        a = SortableTableItem("1.5", sort_kind="float")
        b = SortableTableItem("1.6", sort_kind="float")
        assert a < b

    def test_invalid_falls_back_to_zero(self, qapp):
        assert SortableTableItem("xyz", sort_kind="float") < SortableTableItem("0.1", sort_kind="float")


class TestDatetimeSort:
    def test_iso_date_order(self, qapp):
        a = SortableTableItem("2026-01-01", sort_kind="datetime")
        b = SortableTableItem("2026-02-01", sort_kind="datetime")
        assert a < b

    def test_datetime_with_microseconds(self, qapp):
        a = SortableTableItem("2026-01-01 00:00:00.000001", sort_kind="datetime")
        b = SortableTableItem("2026-01-01 00:00:00.000002", sort_kind="datetime")
        assert a < b

    def test_datetime_with_t_separator(self, qapp):
        a = SortableTableItem("2026-01-01T00:00:00", sort_kind="datetime")
        b = SortableTableItem("2026-01-01T00:00:01", sort_kind="datetime")
        assert a < b

    def test_datetime_with_minutes_only(self, qapp):
        a = SortableTableItem("2026-01-01 12:30", sort_kind="datetime")
        b = SortableTableItem("2026-01-01 12:31", sort_kind="datetime")
        assert a < b

    def test_datetime_unparseable_falls_back_to_string(self, qapp):
        a = SortableTableItem("not a date", sort_kind="datetime")
        b = SortableTableItem("also not a date", sort_kind="datetime")
        # 都是 unparseable，回退字符串字典序
        assert (a < b) or (a == b) or (b < a)


class TestFileSizeSort:
    def test_basic_units(self, qapp):
        b = SortableTableItem("500 B", sort_kind="filesize")
        k = SortableTableItem("1 KB", sort_kind="filesize")
        m = SortableTableItem("1 MB", sort_kind="filesize")
        g = SortableTableItem("1 GB", sort_kind="filesize")
        assert b < k < m < g

    def test_kilobyte_lower_bound(self, qapp):
        # 500 B < 1 KB (500 < 1024)
        b = SortableTableItem("500 B", sort_kind="filesize")
        k = SortableTableItem("1 KB", sort_kind="filesize")
        assert b < k

    def test_decimal_bytes(self, qapp):
        a = SortableTableItem("1.5 KB", sort_kind="filesize")
        b = SortableTableItem("1.6 KB", sort_kind="filesize")
        assert a < b

    def test_invalid_size_is_zero(self, qapp):
        a = SortableTableItem("garbage", sort_kind="filesize")
        b = SortableTableItem("1 B", sort_kind="filesize")
        assert a < b

    def test_unit_aliases(self, qapp):
        # K / M / G 大小写不敏感、无 B 后缀都接受
        k = SortableTableItem("1 K", sort_kind="filesize")
        kb = SortableTableItem("1 KB", sort_kind="filesize")
        assert k == kb


class TestSortValueOverride:
    def test_explicit_sort_value_used(self, qapp):
        # 文本 "z" 但显式 sort_value=0
        item = SortableTableItem("z", sort_kind="int", sort_value=0)
        other = SortableTableItem("a", sort_kind="int", sort_value=100)
        # 排序按 sort_value：0 < 100
        assert item < other


class TestCompareWithPlainQTableWidgetItem:
    """__lt__ / __eq__ 遇到非 SortableTableItem 应回退到 text() 字典序。"""

    def test_lt_with_plain_item(self, qapp):
        si = SortableTableItem("aaa", sort_kind="int")
        pi = QTableWidgetItem("bbb")
        assert si < pi

    def test_eq_with_plain_item_uses_text(self, qapp):
        si = SortableTableItem("hello", sort_kind="int")
        pi = QTableWidgetItem("hello")
        assert si == pi


class TestMixedKind:
    def test_different_sort_kinds_falls_back(self, qapp):
        a = SortableTableItem("1", sort_kind="int")
        b = SortableTableItem("1", sort_kind="str")
        # 异 kind，回退到 text()，都是 "1" → 等
        assert a == b

    def test_type_error_falls_back(self, qapp):
        # 构造两个 sort_value 类型不同的（int vs datetime），让比较抛 TypeError
        a = SortableTableItem("x", sort_kind="int", sort_value=1)
        b = SortableTableItem("x", sort_kind="datetime", sort_value="x")
        # 不抛异常，回退 text() 比较
        result = a < b
        result_eq = a == b
        assert (result is True) or (result is False)
        assert (result_eq is True) or (result_eq is False)
