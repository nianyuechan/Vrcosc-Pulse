import logging
from PySide6.QtGui import QAction

from ..base import Plugin, PluginContext


class HelloPlugin(Plugin):
    name = "HelloPlugin"
    version = "1.0.0"
    description = "示例插件：在托盘菜单中添加一个问候动作。"

    def __init__(self) -> None:
        self._action = None
        self._separator = None

    def activate(self, ctx: PluginContext) -> None:
        mw = ctx.main_window
        logger = logging.getLogger(__name__)
        logger.info("%s activated", self.name)
        try:
            if hasattr(mw, "tray_menu"):
                self._action = QAction("Hello from Plugin", mw)
                self._action.triggered.connect(lambda: logger.info("HelloPlugin triggered"))
                self._separator = mw.tray_menu.addSeparator()
                mw.tray_menu.addAction(self._action)
        except Exception:
            # 非致命，忽略 UI 注入失败
            pass

    def deactivate(self) -> None:
        try:
            # 移除本次添加的分隔线，避免反复启停后累积
            if self._separator is not None:
                menu = self._separator.parent()
                if menu is not None:
                    menu.removeAction(self._separator)
                self._separator = None
            if self._action is not None and self._action.parent() is not None:
                menu = getattr(self._action.parent(), "tray_menu", None)
                if menu is not None:
                    menu.removeAction(self._action)
                self._action = None
        except Exception:
            pass


def plugin_entry():
    return HelloPlugin()
