"""Unit tests for utils.theme_manager.ThemeManager."""
from utils.theme_manager import ThemeManager


def test_auto_theme_uses_detected_system_theme(qapp):
    original_stylesheet = qapp.styleSheet()
    manager = ThemeManager(qapp, system_theme_detector=lambda: "dark")
    try:
        assert manager.set_theme_mode("auto", persist=False) is True
        assert manager.effective_theme == ThemeManager.THEME_DARK
        assert "#0D1117" in qapp.styleSheet()
    finally:
        manager._auto_refresh_timer.stop()
        qapp.setStyleSheet(original_stylesheet)


def test_manual_theme_overrides_system_detection(qapp):
    original_stylesheet = qapp.styleSheet()
    manager = ThemeManager(qapp, system_theme_detector=lambda: "dark")
    try:
        assert manager.set_theme_mode("light", persist=False) is True
        assert manager.effective_theme == ThemeManager.THEME_LIGHT
        assert "#F6F8FA" in qapp.styleSheet()
    finally:
        manager._auto_refresh_timer.stop()
        qapp.setStyleSheet(original_stylesheet)


def test_accent_color_is_validated_and_injected_into_stylesheet(qapp):
    original_stylesheet = qapp.styleSheet()
    manager = ThemeManager(qapp, system_theme_detector=lambda: "light")
    try:
        assert ThemeManager.is_valid_accent_color("#Aa11fF") is True
        assert ThemeManager.is_valid_accent_color("#fff") is False
        assert ThemeManager.is_valid_accent_color("red; color: white") is False
        assert manager.set_accent_color("#Aa11fF", persist=False) is True
        assert manager.accent_color == "#AA11FF"
        assert "#AA11FF" in qapp.styleSheet()
    finally:
        manager._auto_refresh_timer.stop()
        qapp.setStyleSheet(original_stylesheet)


def test_status_style_adapts_to_active_theme(qapp):
    original_stylesheet = qapp.styleSheet()
    manager = ThemeManager(qapp, system_theme_detector=lambda: "dark")
    try:
        manager.set_theme_mode("dark", persist=False)
        assert "#3FB950" in ThemeManager.status_style(success=True)
        manager.set_theme_mode("light", persist=False)
        assert "#1a7f37" in ThemeManager.status_style(success=True)
    finally:
        manager._auto_refresh_timer.stop()
        qapp.setStyleSheet(original_stylesheet)
