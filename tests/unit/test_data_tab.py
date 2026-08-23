"""Tests for the data-management random item actions."""
from unittest.mock import Mock

from ui.tabs import data_tab
from ui.tabs.data_tab import DataTabWidget


def test_open_current_item_uses_photo_url_for_random_name(qtbot, monkeypatch):
    widget = DataTabWidget(None)
    qtbot.addWidget(widget)

    item = {"name": "1234", "source": "test"}
    monkeypatch.setattr(data_tab.FileManager, "load_json_data", lambda: [item])
    monkeypatch.setattr(data_tab.random, "choice", lambda data: data[0])
    browser_open = Mock(return_value=True)
    monkeypatch.setattr(data_tab.webbrowser, "open", browser_open)

    widget._on_get_random_item()
    assert widget.current_random_item == item
    assert widget.open_current_button.isEnabled()

    widget._on_open_current_item()

    browser_open.assert_called_once_with(
        "https://18comic.vip/photo/1234",
        new=2,
    )
