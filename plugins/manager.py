from __future__ import annotations

import importlib
import importlib.util
import logging
import pkgutil
from typing import List, Any

try:
    # Python 3.8+
    from importlib.metadata import entry_points
except Exception:  # pragma: no cover
    entry_points = None  # type: ignore

from .base import Plugin, PluginContext


logger = logging.getLogger(__name__)


PLUGIN_ENTRYPOINT_GROUP = "vrcosc_pulse.plugins"


def _module_available(name: str) -> bool:
    """检查 Python 模块/包是否已安装（不实际导入）。"""
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, AttributeError, ValueError):
        return False


class PluginManager:
    """插件管理器：负责发现、注册与管理插件生命周期与依赖。

    变更：
    - 加载（发现）插件后默认不启用，由用户在插件设置中手动启用。
    - 启用前自动检查依赖（其他插件或 Python 模块）；缺失时返回可操作的安装提示。
    - 提供 install/update/uninstall 操作（调用插件可选方法）。
    """

    def __init__(self, ctx: PluginContext) -> None:
        self.ctx = ctx
        self._plugins: List[Plugin] = []
        self._active: set[str] = set()

    @property
    def plugins(self) -> List[Plugin]:
        return list(self._plugins)

    def load_all(self) -> None:
        """通过入口点与本地扫描发现插件并注册；默认全部不启用。"""
        collected: List[Plugin] = []
        collected.extend(self._collect_from_entry_points())
        collected.extend(self._collect_from_local_packages())
        for plugin in collected:
            self._register(plugin)
        for plugin in self._plugins:
            ok, missing = self._check_dependencies(plugin)
            if not ok:
                for item in missing:
                    logger.warning(
                        "Plugin '%s' dependency '%s' not ready: %s",
                        getattr(plugin, "name", "<unknown>"),
                        item["dep"],
                        item["hint"],
                    )
        logger.info("PluginManager registered %d plugin(s); all disabled by default", len(self._plugins))

    # --- discovery strategies ---
    def _collect_from_entry_points(self) -> List[Plugin]:
        collected: List[Plugin] = []
        if entry_points is None:
            logger.debug("importlib.metadata.entry_points unavailable; skip entry point discovery")
            return []
        try:
            eps = entry_points()
            # Support different importlib.metadata APIs across Python versions
            candidates = []
            if hasattr(eps, "select"):
                candidates = list(eps.select(group=PLUGIN_ENTRYPOINT_GROUP))
            elif isinstance(eps, dict):
                candidates = list(eps.get(PLUGIN_ENTRYPOINT_GROUP, []))
            else:
                candidates = [e for e in eps if getattr(e, "group", None) == PLUGIN_ENTRYPOINT_GROUP]
        except Exception as e:
            logger.warning("Failed to read entry points: %s", e)
            return []

        for ep in candidates:
            try:
                obj = ep.load()
                plugin = self._coerce_to_plugin(obj)
                if plugin is None:
                    logger.warning("Entry point '%s' did not produce a Plugin", getattr(ep, "name", "<unknown>"))
                    continue
                collected.append(plugin)
                logger.info("Discovered plugin via entry point: %s", plugin.name)
            except Exception as e:
                logger.exception("Failed to load plugin from entry point '%s': %s", getattr(ep, "name", "<unknown>"), e)
        return collected

    def _collect_from_local_packages(self) -> List[Plugin]:
        """扫描本地 'plugins.local' 子包中的插件。

        开发者可将插件模块放置于 'plugins/local/' 目录，模块需暴露：
        - 'plugin_entry' 可调用对象，返回实现 Plugin 接口的实例；或
        - 'Plugin' 类（可无参构造），实现 Plugin 接口。
        """
        collected: List[Plugin] = []
        try:
            pkg = importlib.import_module("plugins.local")
        except ModuleNotFoundError:
            return []
        except Exception as e:
            logger.warning("plugins.local import failed: %s", e)
            return []

        for modinfo in pkgutil.iter_modules(pkg.__path__):
            name = modinfo.name
            full_name = f"plugins.local.{name}"
            try:
                module = importlib.import_module(full_name)
                obj = getattr(module, "plugin_entry", None)
                plugin: Plugin | None = None
                if callable(obj):
                    plugin = obj()
                else:
                    cls = getattr(module, "Plugin", None)
                    if cls is not None:
                        plugin = cls()  # type: ignore
                if plugin is None:
                    logger.warning("Local plugin '%s' not found 'plugin_entry' or 'Plugin'", full_name)
                    continue
                collected.append(plugin)
                logger.info("Discovered local plugin: %s", plugin.name)
            except Exception as e:
                logger.exception("Failed to load local plugin '%s': %s", full_name, e)
        return collected

    # --- registration & dependency checking ---
    def _register(self, plugin: Plugin) -> None:
        """注册插件；默认不启用，只等用户在设置中手动启用。"""
        name = getattr(plugin, "name", "<unknown>")
        # 重名检测：同名插件会导致启用/停用目标不明确，直接拒绝第二个
        if self._find_plugin(name) is not None:
            logger.warning("Plugin name '%s' already registered; skipping duplicate", name)
            return
        try:
            plugin.enabled = False
        except Exception:
            pass
        if plugin not in self._plugins:
            self._plugins.append(plugin)
        logger.info("Registered plugin (disabled by default): %s", name)

    def _find_plugin(self, name: str) -> Plugin | None:
        for p in self._plugins:
            try:
                if getattr(p, "name", None) == name:
                    return p
            except Exception:
                continue
        return None

    def _check_dependencies(self, plugin: Plugin) -> tuple[bool, list[dict[str, str]]]:
        """检查插件依赖是否可用：其他插件（需已启用）或 Python 模块（需已安装）。"""
        missing: list[dict[str, str]] = []
        for raw in getattr(plugin, "requires", None) or []:
            dep = str(raw).strip()
            if not dep:
                continue
            dep_plugin = self._find_plugin(dep)
            if dep_plugin is not None:
                if dep in self._active:
                    continue
                missing.append({
                    "dep": dep,
                    "reason": "disabled",
                    "hint": f"请先在插件设置中启用「{dep}」",
                })
                continue
            if _module_available(dep):
                continue
            missing.append({
                "dep": dep,
                "reason": "missing",
                "hint": (
                    f"未找到依赖「{dep}」。若是 Python 包，请运行 pip install {dep}；"
                    f"若是插件，请先安装插件「{dep}」"
                ),
            })
        return not missing, missing

    def set_plugin_enabled(self, name: str, enabled: bool) -> tuple[bool, str]:
        """启用/停用插件。启用前自动检查依赖，缺失时返回安装/启用提示。"""
        plugin = self._find_plugin(name)
        if plugin is None:
            return False, f"未找到插件「{name}」"
        if not enabled:
            if name in self._active:
                try:
                    plugin.deactivate()
                except Exception as e:
                    logger.exception("Failed to deactivate plugin '%s': %s", name, e)
                self._active.discard(name)
            try:
                plugin.enabled = False
            except Exception:
                pass
            return True, ""
        if name in self._active:
            return True, ""
        ok, missing = self._check_dependencies(plugin)
        if not ok:
            return False, "；".join(item["hint"] for item in missing)
        try:
            plugin.activate(self.ctx)
        except Exception as e:
            logger.exception("Failed to activate plugin '%s': %s", name, e)
            return False, f"插件「{name}」启用失败：{e}"
        self._active.add(name)
        try:
            plugin.enabled = True
        except Exception:
            pass
        logger.info("Plugin enabled: %s", name)
        return True, ""

    # --- utils ---
    def _coerce_to_plugin(self, obj: Any) -> Plugin | None:
        try:
            # 入口点直接指向插件类：无参实例化
            if isinstance(obj, type):
                if hasattr(obj, "activate") and hasattr(obj, "deactivate"):
                    return obj()  # type: ignore
                return None
            if callable(obj):
                # 工厂：优先 factory(ctx)，签名不符时回退无参 factory()
                try:
                    res = obj(self.ctx)  # type: ignore
                except TypeError:
                    res = None
                if res is None:
                    try:
                        res = obj()  # type: ignore
                    except TypeError:
                        return None
                if hasattr(res, "activate") and hasattr(res, "deactivate"):
                    return res  # type: ignore
            # 入口点直接指向插件实例
            if hasattr(obj, "activate") and hasattr(obj, "deactivate"):
                return obj  # type: ignore
        except Exception:
            pass
        return None

    # --- lifecycle operations ---
    def install(self, plugin: Plugin) -> None:
        try:
            fn = getattr(plugin, "install", None)
            if callable(fn):
                fn(self.ctx)
            self._register(plugin)
        except Exception as e:
            logger.exception("Plugin install failed for %s: %s", getattr(plugin, "name", "<unknown>"), e)

    def update(self, plugin: Plugin) -> None:
        try:
            fn = getattr(plugin, "update", None)
            if callable(fn):
                fn(self.ctx)
        except Exception as e:
            logger.exception("Plugin update failed for %s: %s", getattr(plugin, "name", "<unknown>"), e)

    def uninstall(self, plugin: Plugin) -> None:
        try:
            name = getattr(plugin, "name", "<unknown>")
            try:
                plugin.deactivate()
            except Exception:
                pass
            self._active.discard(name)
            fn = getattr(plugin, "uninstall", None)
            if callable(fn):
                fn()
            try:
                self._plugins.remove(plugin)
            except ValueError:
                pass
            # 卸载后同步持久化的启用列表，避免下次启动恢复时报警告
            try:
                mw = getattr(self.ctx, "main_window", None)
                if mw is not None and hasattr(mw, "_save_settings"):
                    mw._save_settings()
            except Exception:
                pass
        except Exception as e:
            logger.exception("Plugin uninstall failed for %s: %s", getattr(plugin, "name", "<unknown>"), e)
