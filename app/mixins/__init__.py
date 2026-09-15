"""MainWindow 拆分出的功能模块（mixin）。"""

from .wallpaper import WallpaperMixin
from .theme import ThemeMixin
from .osc import OscMixin
from .sending import SendingMixin
from .history import HistoryMixin
from .debug import DebugMixin
from .tray import TrayMixin

__all__ = [
    "WallpaperMixin", "ThemeMixin", "OscMixin", "SendingMixin",
    "HistoryMixin", "DebugMixin", "TrayMixin",
]
