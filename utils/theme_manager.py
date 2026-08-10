"""Central application theme management for light, dark, and automatic modes."""
import re
import sys
from typing import Callable, Dict, Optional

from PyQt5.QtCore import QObject, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QGuiApplication, QPalette
from PyQt5.QtWidgets import QApplication

from utils.config import Config
from utils.logger import logger


class ThemeManager(QObject):
    """Own application colors, persisted preferences, and OS-theme synchronization."""

    THEME_LIGHT = "light"
    THEME_DARK = "dark"
    THEME_AUTO = "auto"
    VALID_THEME_MODES = (THEME_LIGHT, THEME_DARK, THEME_AUTO)
    DEFAULT_ACCENT_COLOR = "#4F7CFF"
    ACCENT_PRESETS = (
        ("\u54c1\u724c\u84dd", "#4F7CFF"),
        ("\u5929\u7a7a\u9752", "#00A6A6"),
        ("\u6d3b\u529b\u7d2b", "#8B5CF6"),
        ("\u6696\u9633\u6a59", "#E67E22"),
        ("\u81ea\u7136\u7eff", "#2E9B5F"),
    )
    AUTO_REFRESH_INTERVAL_MS = 2000

    theme_changed = pyqtSignal(str, str)
    _instance = None
    _active_theme = THEME_LIGHT
    _active_colors = None

    def __init__(self, app: QApplication, system_theme_detector: Optional[Callable[[], str]] = None) -> None:
        super().__init__(app)
        self._app = app
        self._system_theme_detector = system_theme_detector
        self._theme_mode = Config.get_theme_mode()
        self._accent_color = Config.get_accent_color()
        self._effective_theme = self.THEME_LIGHT
        self._auto_refresh_timer = QTimer(self)
        self._auto_refresh_timer.setInterval(self.AUTO_REFRESH_INTERVAL_MS)
        self._auto_refresh_timer.timeout.connect(self.refresh_system_theme)
        self._connect_native_theme_signal()
        self.apply_theme(force=True)

    @classmethod
    def initialize(cls, app: Optional[QApplication] = None) -> "ThemeManager":
        """Create the application singleton after QApplication exists."""
        app = app or QApplication.instance()
        if app is None:
            raise RuntimeError("ThemeManager requires an existing QApplication")
        if cls._instance is None or cls._instance._app is not app:
            cls._instance = cls(app)
        return cls._instance

    @classmethod
    def instance(cls) -> Optional["ThemeManager"]:
        return cls._instance

    @classmethod
    def get_or_create(cls) -> "ThemeManager":
        return cls.initialize()

    @classmethod
    def is_valid_accent_color(cls, color: object) -> bool:
        """Accept only a literal #RRGGBB value before it reaches QSS."""
        return isinstance(color, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", color) is not None

    @classmethod
    def normalize_accent_color(cls, color: object) -> str:
        return str(color).upper() if cls.is_valid_accent_color(color) else cls.DEFAULT_ACCENT_COLOR

    @property
    def theme_mode(self) -> str:
        return self._theme_mode

    @property
    def effective_theme(self) -> str:
        return self._effective_theme

    @property
    def accent_color(self) -> str:
        return self._accent_color

    def set_theme_mode(self, theme_mode: str, persist: bool = True) -> bool:
        normalized = str(theme_mode).lower()
        if normalized not in self.VALID_THEME_MODES:
            return False
        if persist and not Config.set_theme_mode(normalized):
            logger.warning("Theme preference could not be saved; using it for this session only")
        self._theme_mode = normalized
        self.apply_theme(force=True)
        return True

    def set_accent_color(self, color: str, persist: bool = True) -> bool:
        if not self.is_valid_accent_color(color):
            return False
        normalized = self.normalize_accent_color(color)
        if persist and not Config.set_accent_color(normalized):
            logger.warning("Accent color could not be saved; using it for this session only")
        self._accent_color = normalized
        self.apply_theme(force=True)
        return True

    def reset_accent_color(self) -> bool:
        return self.set_accent_color(self.DEFAULT_ACCENT_COLOR)

    def refresh_system_theme(self) -> None:
        """Repaint only if an Auto-mode system-theme transition was detected."""
        if self._theme_mode == self.THEME_AUTO:
            self.apply_theme(force=False)

    def apply_theme(self, force: bool = False) -> None:
        effective_theme = self._resolve_effective_theme()
        if not force and effective_theme == self._effective_theme:
            return
        self._effective_theme = effective_theme
        colors = self._build_colors(effective_theme, self._accent_color)
        self._apply_palette(colors)
        self._app.setStyleSheet(self._build_style_sheet(colors))
        self.__class__._active_theme = effective_theme
        self.__class__._active_colors = colors
        self._configure_auto_refresh()
        self.theme_changed.emit(self._theme_mode, self._accent_color)

    def _configure_auto_refresh(self) -> None:
        if self._theme_mode == self.THEME_AUTO:
            if not self._auto_refresh_timer.isActive():
                self._auto_refresh_timer.start()
        else:
            self._auto_refresh_timer.stop()

    def _resolve_effective_theme(self) -> str:
        if self._theme_mode in (self.THEME_LIGHT, self.THEME_DARK):
            return self._theme_mode
        return self._detect_system_theme()

    def _connect_native_theme_signal(self) -> None:
        """Use a future Qt color-scheme signal when the runtime actually exposes it."""
        try:
            hints = QGuiApplication.styleHints()
            signal = getattr(hints, "colorSchemeChanged", None)
            if signal is not None:
                signal.connect(lambda *_: self.refresh_system_theme())
        except Exception:
            # PyQt5/Qt 5.15 has no colorScheme API; the timer is its fallback.
            pass

    def _detect_system_theme(self) -> str:
        if self._system_theme_detector is not None:
            detected = self._system_theme_detector()
            if detected in (self.THEME_LIGHT, self.THEME_DARK):
                return detected
        detected = self._read_qt_color_scheme() or self._read_windows_theme()
        if detected is not None:
            return detected
        try:
            return self.THEME_DARK if self._app.palette().color(QPalette.Window).lightness() < 128 else self.THEME_LIGHT
        except Exception:
            return self.THEME_LIGHT

    @staticmethod
    def _read_qt_color_scheme() -> Optional[str]:
        try:
            hints = QGuiApplication.styleHints()
            method = getattr(hints, "colorScheme", None)
            if method is None:
                return None
            scheme = method()
            name = getattr(scheme, "name", str(scheme)).lower()
            if "dark" in name:
                return ThemeManager.THEME_DARK
            if "light" in name:
                return ThemeManager.THEME_LIGHT
        except Exception:
            return None
        return None

    @staticmethod
    def _read_windows_theme() -> Optional[str]:
        if not sys.platform.startswith("win"):
            return None
        try:
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return ThemeManager.THEME_LIGHT if int(value) else ThemeManager.THEME_DARK
        except (ImportError, OSError, ValueError, TypeError):
            return None

    @staticmethod
    def _mix(base: str, overlay: str, ratio: float) -> str:
        base_color, overlay_color = QColor(base), QColor(overlay)
        ratio = max(0.0, min(1.0, ratio))
        return QColor(
            round(base_color.red() * (1 - ratio) + overlay_color.red() * ratio),
            round(base_color.green() * (1 - ratio) + overlay_color.green() * ratio),
            round(base_color.blue() * (1 - ratio) + overlay_color.blue() * ratio),
        ).name().upper()

    @classmethod
    def _build_colors(cls, theme: str, accent: str) -> Dict[str, str]:
        accent = cls.normalize_accent_color(accent)
        accent_color = QColor(accent)
        if theme == cls.THEME_DARK:
            colors = {
                "window": "#0D1117", "surface": "#161B22", "surface_alt": "#21262D",
                "surface_hover": "#30363D", "border": "#30363D", "text": "#E6EDF3",
                "muted": "#8B949E", "disabled_text": "#6E7681", "selection_text": "#FFFFFF",
                "success": "#3FB950", "success_bg": "#12261E", "danger": "#F85149", "danger_bg": "#2D1215",
            }
            colors.update({
                "accent": accent,
                "accent_hover": accent_color.lighter(115).name().upper(),
                "accent_pressed": accent_color.darker(120).name().upper(),
                "accent_soft": cls._mix("#161B22", accent, 0.28),
            })
        else:
            colors = {
                "window": "#F6F8FA", "surface": "#FFFFFF", "surface_alt": "#F6F8FA",
                "surface_hover": "#EAEEF2", "border": "#D0D7DE", "text": "#1F2328",
                "muted": "#57606A", "disabled_text": "#8C959F", "selection_text": "#FFFFFF",
                "success": "#1a7f37", "success_bg": "#dafbe1", "danger": "#cf222e", "danger_bg": "#ffebe9",
            }
            colors.update({
                "accent": accent,
                "accent_hover": accent_color.darker(108).name().upper(),
                "accent_pressed": accent_color.darker(122).name().upper(),
                "accent_soft": cls._mix("#FFFFFF", accent, 0.12),
            })
        return colors

    def _apply_palette(self, colors: Dict[str, str]) -> None:
        palette = self._app.palette()
        palette.setColor(QPalette.Window, QColor(colors["window"]))
        palette.setColor(QPalette.WindowText, QColor(colors["text"]))
        palette.setColor(QPalette.Base, QColor(colors["surface"]))
        palette.setColor(QPalette.AlternateBase, QColor(colors["surface_alt"]))
        palette.setColor(QPalette.ToolTipBase, QColor(colors["surface"]))
        palette.setColor(QPalette.ToolTipText, QColor(colors["text"]))
        palette.setColor(QPalette.Text, QColor(colors["text"]))
        palette.setColor(QPalette.Button, QColor(colors["surface_alt"]))
        palette.setColor(QPalette.ButtonText, QColor(colors["text"]))
        palette.setColor(QPalette.Highlight, QColor(colors["accent"]))
        palette.setColor(QPalette.HighlightedText, QColor(colors["selection_text"]))
        palette.setColor(QPalette.Disabled, QPalette.Text, QColor(colors["disabled_text"]))
        palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(colors["disabled_text"]))
        self._app.setPalette(palette)

    @classmethod
    def status_style(cls, success: Optional[bool] = None, running: bool = False) -> str:
        colors = cls._active_colors or cls._build_colors(cls.THEME_LIGHT, cls.DEFAULT_ACCENT_COLOR)
        if success is True:
            return "font-weight: bold; color: {success}; background: {success_bg}; padding: 4px;".format(**colors)
        if success is False:
            return "font-weight: bold; color: {danger}; background: {danger_bg}; padding: 4px;".format(**colors)
        return "font-weight: bold; color: {0}; padding: 4px;".format(colors["accent"] if running else colors["muted"])

    @staticmethod
    def _build_style_sheet(colors: Dict[str, str]) -> str:
        template = """
QWidget { background-color: @window; color: @text; }
QMainWindow, QDialog, QMessageBox { background-color: @window; }
QLabel#previewInfoLabel, QLabel#previewCounterLabel { color: @muted; font-size: 12px; }
QLabel#trashStatsLabel { color: @muted; padding: 5px; }
QLabel#trashHintLabel { color: @muted; font-size: 11px; }
QMenuBar { background-color: @surface; color: @text; border-bottom: 1px solid @border; }
QMenuBar::item { background: transparent; padding: 5px 9px; }
QMenuBar::item:selected, QMenu::item:selected { background-color: @accent_soft; color: @text; }
QMenu { background-color: @surface; color: @text; border: 1px solid @border; padding: 4px; }
QMenu::item { padding: 6px 24px 6px 12px; border-radius: 3px; }
QMenu::separator { height: 1px; background: @border; margin: 4px 8px; }
QStatusBar { background-color: @surface; color: @muted; border-top: 1px solid @border; }
QTabWidget::pane { border: 1px solid @border; background: @surface; }
QTabWidget#mainTabWidget::pane { padding: 0; margin: 0; border: 0; }
QTabBar::tab { background: @surface_alt; color: @muted; border: 1px solid @border; border-bottom: none; padding: 7px 14px; margin-right: 2px; border-top-left-radius: 4px; border-top-right-radius: 4px; }
QTabBar::tab:selected { background: @surface; color: @text; border-top: 2px solid @accent; }
QTabBar::tab:hover:!selected { background: @surface_hover; color: @text; }
QPushButton { background-color: @surface_alt; color: @text; border: 1px solid @border; border-radius: 4px; padding: 6px 12px; }
QPushButton:hover { background-color: @surface_hover; border-color: @accent; }
QPushButton:pressed { background-color: @accent_soft; border-color: @accent_pressed; }
QPushButton:disabled { color: @disabled_text; background-color: @surface_alt; border-color: @border; }
QPushButton[compact="true"] { padding: 0; margin: 0; }
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox, QDateEdit, QTimeEdit, QDateTimeEdit { background-color: @surface; color: @text; border: 1px solid @border; border-radius: 4px; padding: 5px 7px; selection-background-color: @accent; selection-color: @selection_text; }
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QDateEdit:focus, QTimeEdit:focus, QDateTimeEdit:focus { border: 1px solid @accent; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView { background-color: @surface; color: @text; selection-background-color: @accent; selection-color: @selection_text; border: 1px solid @border; }
QAbstractItemView, QTableView, QListView, QTreeView, QTableWidget, QListWidget { background-color: @surface; alternate-background-color: @surface_alt; color: @text; border: 1px solid @border; selection-background-color: @accent; selection-color: @selection_text; gridline-color: @border; }
QAbstractItemView::item:hover { background-color: @accent_soft; }
QHeaderView::section { background-color: @surface_alt; color: @text; border: none; border-right: 1px solid @border; border-bottom: 1px solid @border; padding: 6px; }
QGroupBox { color: @text; border: 1px solid @border; border-radius: 5px; margin-top: 12px; padding: 10px; padding-top: 16px; }
QGroupBox::title { subcontrol-origin: margin; left: 9px; padding: 0 4px; }
QCheckBox, QRadioButton { color: @text; spacing: 6px; }
QCheckBox::indicator, QRadioButton::indicator { width: 15px; height: 15px; }
QCheckBox::indicator:unchecked, QRadioButton::indicator:unchecked { background: @surface; border: 1px solid @border; }
QCheckBox::indicator:checked, QRadioButton::indicator:checked { background: @accent; border: 1px solid @accent; }
QProgressBar { background-color: @surface_alt; color: @text; border: 1px solid @border; border-radius: 4px; text-align: center; }
QProgressBar::chunk { background-color: @accent; border-radius: 3px; }
QSlider::groove:horizontal { background: @surface_alt; height: 5px; border-radius: 2px; }
QSlider::handle:horizontal { background: @accent; width: 14px; margin: -5px 0; border-radius: 7px; }
QScrollBar:vertical { background: @surface_alt; width: 12px; margin: 0; }
QScrollBar::handle:vertical { background: @border; min-height: 24px; border-radius: 5px; }
QScrollBar::handle:vertical:hover { background: @muted; }
QScrollBar:horizontal { background: @surface_alt; height: 12px; margin: 0; }
QScrollBar::handle:horizontal { background: @border; min-width: 24px; border-radius: 5px; }
QScrollBar::handle:horizontal:hover { background: @muted; }
QToolTip { background-color: @surface_alt; color: @text; border: 1px solid @border; padding: 4px; }
QSplitter::handle { background-color: @border; }
"""
        # Replace longer tokens first so @accent cannot consume @accent_soft.
        for key in sorted(colors, key=len, reverse=True):
            template = template.replace("@" + key, colors[key])
        return template
