"""跨平台系统通知适配器。

设计目标：
1. 任意平台都能调用，导入时不会因为 win10toast 缺失而崩。
2. 资源随主进程退出而释放。
3. 多种实现并存，依次降级：
   - QSystemTrayIcon（所有平台，PyQt5 自带，零依赖）
   - 兜底 log + stdout

历史上 win10toast 在 Windows 下使用更现代的 Toast 通知，但其
show_toast(threaded=True) 启守护线程的方式在 Python 解释器关闭
阶段会触发 WNDPROC 错误（"WPARAM is simple, so must be an int
object (got NoneType)"）。QSystemTrayIcon 没有这个问题，且能
覆盖 Win7/10/11/macOS/Linux，是更稳的默认选择。
"""
import os
import sys
import threading
from typing import Optional

from utils.logger import logger


# 平台探测（保留以便将来按平台调样式）
_PLATFORM = sys.platform
_IS_WINDOWS = _PLATFORM.startswith("win")
_IS_MAC = _PLATFORM == "darwin"
_IS_LINUX = _PLATFORM.startswith("linux")


class _BaseBackend:
    """后端基类：定义 shutdown/notify 接口。"""
    name = "base"

    def notify(self, title: str, message: str, duration: int = 5) -> bool:  # pragma: no cover
        return False

    def shutdown(self) -> None:  # pragma: no cover
        pass


class _QSystemTrayIconBackend(_BaseBackend):
    """跨平台统一后端：使用 QSystemTrayIcon。

    - 必须在 QApplication 已存在的前提下才能用，否则 self._tray 留 None
    - 不要在 shutdown 里调 deleteLater()，让 QApplication 析构时自然回收
    - 必须 setFocusPolicy + 显式 hide()，避免 Python 退出时未释放的窗口
      句柄触发 WNDPROC 错误
    """

    name = "qsystemtrayicon"

    def __init__(self):
        self._tray = None
        self._init_lock = threading.Lock()
        self._init_once()

    def _init_once(self) -> None:
        with self._init_lock:
            if self._tray is not None:
                return
            try:
                from PyQt5.QtWidgets import QApplication, QSystemTrayIcon  # type: ignore
                from PyQt5.QtGui import QIcon  # type: ignore

                app = QApplication.instance()
                if app is None:
                    logger.debug("QSystemTrayIcon 不可用：无 QApplication")
                    return

                if not QSystemTrayIcon.isSystemTrayAvailable():
                    logger.debug("QSystemTrayIcon 不可用：系统托盘不可用")
                    return

                # QSystemTrayIcon(QIcon(), app) — 第二个参数是 parent
                # parent=QApplication 之后，QApplication 析构时会回收这个 icon
                self._tray = QSystemTrayIcon(QIcon(), app)
                self._tray.setToolTip("天堂图片管理器")
                self._tray.show()
            except Exception as e:
                logger.debug(f"QSystemTrayIcon 初始化失败: {e}")
                self._tray = None

    def notify(self, title: str, message: str, duration: int = 5) -> bool:
        if self._tray is None:
            return False
        try:
            from PyQt5.QtWidgets import QSystemTrayIcon  # type: ignore
            self._tray.showMessage(
                title,
                message,
                QSystemTrayIcon.Information,
                int(duration * 1000),
            )
            return True
        except Exception as e:
            logger.warning(f"QSystemTrayIcon.showMessage 失败: {e}")
            return False

    def shutdown(self) -> None:
        # QSystemTrayIcon 已挂在 QApplication 上，QApplication 析构时会回收。
        # 这里只 hide() + 解引用，绝不 deleteLater()（见类级注释）。
        if self._tray is not None:
            try:
                self._tray.hide()
            except Exception:
                pass
            self._tray = None


class _LogBackend(_BaseBackend):
    """最后兜底：写到日志 + stdout。"""

    name = "log"

    def notify(self, title: str, message: str, duration: int = 5) -> bool:
        try:
            line = f"[notify] {title} - {message}"
            logger.info(line)
            # 兜底再打印到 stdout，便于无 GUI 环境也能看到
            try:
                print(line)
            except Exception:
                pass
            return True
        except Exception:
            return False


class Notifier:
    """统一通知门面：内部按平台选后端，按顺序降级。

    使用方式：
        from utils.notifier import notifier
        notifier.notify("标题", "正文")
        # 应用退出前
        notifier.shutdown()
    """

    def __init__(self):
        self._backends: list = []
        self._init_lock = threading.Lock()
        self._initialized = False
        self._init_backends()

    def _init_backends(self) -> None:
        with self._init_lock:
            if self._initialized:
                return
            self._initialized = True

            # 优先级：QSystemTrayIcon（所有平台）→ log 兜底
            # 不再使用 win10toast：其 threaded=True 的守护线程会在
            # Python 退出时触发 WNDPROC 错误（None WPARAM）
            self._backends.append(_QSystemTrayIconBackend())
            self._backends.append(_LogBackend())

    def notify(self, title: str, message: str, duration: int = 5) -> bool:
        """按后端顺序尝试发送通知；任一成功即返回 True。"""
        if not self._backends:
            self._init_backends()
        for backend in self._backends:
            try:
                if backend.notify(title, message, duration):
                    logger.debug(f"通知已通过 {backend.name} 发送: {title}")
                    return True
            except Exception as e:
                logger.warning(f"通知后端 {backend.name} 抛异常: {e}")
                continue
        return False

    def shutdown(self) -> None:
        """释放所有后端持有的资源。

        关于 Qt 关闭阶段的注意点：
        1. 不要对 QObject 调 deleteLater()，原因：
           aboutToQuit 触发时 PyQt5 可能已经在拆模块，延后事件执行时
           回调收到的 WPARAM / LPARAM 已经是 None，会抛
           "WNDPROC return value cannot be converted to LRESULT" /
           "WPARAM is simple, so must be an int object (got NoneType)"。
        2. QSystemTrayIcon 已经是 QApplication 的子对象，QApplication
           析构时自然回收即可，无需我们显式 delete。
        这里只做轻量 hide() + 解引用，让 GC + QApplication 析构来收尾。
        整个过程不能向上抛异常（解释器退出阶段调到这里，不能再 raise）。
        """
        for backend in self._backends:
            try:
                backend.shutdown()
            except Exception as e:
                try:
                    logger.debug(f"关闭通知后端 {backend.name} 失败: {e}")
                except Exception:
                    pass


# 全局单例
notifier = Notifier()
