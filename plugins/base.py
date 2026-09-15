from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, List, Any


@dataclass
class PluginContext:
    """插件运行上下文。

    - app: Qt 应用对象
    - main_window: 主窗口实例，用于访问 UI/状态
    """

    app: object
    main_window: object


class Plugin(Protocol):
    """插件接口定义。

    插件需实现以下方法以参与系统生命周期。
    """

    name: str
    version: str
    description: str
    author: Optional[str]
    homepage: Optional[str]
    # 依赖的其他插件名称（可选），用于依赖解析与按序激活
    requires: List[str]

    def activate(self, ctx: PluginContext) -> None:
        """插件被加载后调用，用于注册 UI/功能。"""

    def deactivate(self) -> None:
        """插件卸载前调用，用于清理资源。"""

    # --- 生命周期增强（可选实现） ---
    def install(self, ctx: PluginContext) -> None:
        """安装插件：下载/拷贝资源、初始化配置等。默认可不实现。"""

    def update(self, ctx: PluginContext) -> None:
        """更新插件：迁移数据、刷新资源等。默认可不实现。"""

    def uninstall(self) -> None:
        """卸载插件：清理文件与状态。默认可不实现。"""

    # --- 配置界面支持（可选实现） ---
    def create_settings_widget(self, parent: Any) -> Any:
        """返回一个 QWidget 用于插件配置；不支持时返回 None。"""
