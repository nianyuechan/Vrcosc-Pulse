import logging

try:
    from PySide6.QtGui import QAction
except Exception:
    QAction = None  # type: ignore

from ..base import Plugin, PluginContext


def _get_console_hwnd():
    try:
        import ctypes as _ct
        return _ct.windll.kernel32.GetConsoleWindow()
    except Exception:
        return 0


def _show_console(show: bool) -> None:
    try:
        import ctypes as _ct
        hwnd = _get_console_hwnd()
        if hwnd:
            _ct.windll.user32.ShowWindow(hwnd, 5 if show else 0)  # SW_SHOW / SW_HIDE
    except Exception:
        pass


class HideConsolePlugin(Plugin):
    name = "HideConsolePlugin"
    version = "1.0.0"
    description = "启动时隐藏控制台窗口，并在托盘菜单提供显示/隐藏切换。"

    def __init__(self) -> None:
        self._toggle_action = None
        self._separator = None
        self._visible = False

    def activate(self, ctx: PluginContext) -> None:
        logger = logging.getLogger(__name__)
        logger.info("%s activated", self.name)
        # 启动时隐藏控制台窗口（仅 Windows 有效）
        _show_console(False)

        # 在托盘菜单中增加控制台显示/隐藏的切换
        try:
            mw = ctx.main_window
            if QAction is not None and hasattr(mw, "tray_menu"):
                self._toggle_action = QAction("显示控制台窗口", mw)
                self._toggle_action.triggered.connect(self._on_toggle)
                self._separator = mw.tray_menu.addSeparator()
                mw.tray_menu.addAction(self._toggle_action)
        except Exception:
            # 非致命：托盘菜单不可用时忽略
            pass

    def _on_toggle(self) -> None:
        try:
            self._visible = not self._visible
            _show_console(self._visible)
            if self._toggle_action is not None:
                self._toggle_action.setText("隐藏控制台窗口" if self._visible else "显示控制台窗口")
        except Exception:
            pass

    def deactivate(self) -> None:
        try:
            # 移除本次添加的分隔线，避免反复启停后累积
            if self._separator is not None:
                menu = self._separator.parent()
                if menu is not None:
                    menu.removeAction(self._separator)
                self._separator = None
            if self._toggle_action is not None:
                parent = self._toggle_action.parent()
                if parent is not None and hasattr(parent, "tray_menu"):
                    parent.tray_menu.removeAction(self._toggle_action)
                self._toggle_action = None
        except Exception:
            pass


def plugin_entry():
    return HideConsolePlugin()
