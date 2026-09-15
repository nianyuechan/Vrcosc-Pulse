"""VRCOSC Pulse 插件系统入口包。

包含插件基类与插件管理器，用于自动发现与加载第三方或本地插件。
"""

from .base import Plugin, PluginContext
from .manager import PluginManager

__all__ = [
    "Plugin",
    "PluginContext",
    "PluginManager",
]

