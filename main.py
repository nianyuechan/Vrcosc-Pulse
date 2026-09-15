import logging
import os
import sys

from PySide6.QtWidgets import QApplication

APP_NAME = "VRCOSC Pulse"


def _configure_logging() -> None:
    handlers: list[logging.Handler] = []
    if sys.stdout is not None:
        # 有控制台（源码/调试运行时）：输出到 stdout
        handlers.append(logging.StreamHandler(sys.stdout))
    else:
        # 打包为窗口程序时没有控制台：写入用户目录日志文件，便于排查
        try:
            log_path = os.path.join(os.path.expanduser("~"), ".vrcosc_pulse.log")
            handlers.append(logging.FileHandler(log_path, encoding="utf-8"))
        except Exception:
            handlers.append(logging.NullHandler())
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )


def main() -> int:
    """Package entrypoint loading MainWindow from the app package."""
    _configure_logging()

    app = QApplication(sys.argv)
    try:
        from app.main_window import MainWindow
    except Exception as e:
        logging.getLogger(__name__).exception("Failed to import MainWindow: %s", e)
        return 1

    window = MainWindow()
    # 初始化插件系统并保留管理器引用，供设置页与运行时操作使用
    try:
        from plugins import PluginContext, PluginManager

        ctx = PluginContext(app=app, main_window=window)
        pm = PluginManager(ctx)
        pm.load_all()
        try:
            setattr(window, "plugin_manager", pm)
        except Exception:
            pass
        try:
            window._restore_plugins_from_prefs()
        except Exception as e:
            logging.getLogger(__name__).warning("Restore plugin settings failed: %s", e)
    except Exception as e:
        logging.getLogger(__name__).warning("Plugin system init failed: %s", e)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
