from typing import Optional

from plugins.base import Plugin

try:
    from PySide6.QtGui import QShortcut, QKeySequence
    from PySide6.QtCore import QTimer
except Exception:  # Fallback for environments without PySide6 available at import time
    QShortcut = None
    QKeySequence = None
    QTimer = None


class PauseOnYPlugin(Plugin):
    name = "PauseOnYPlugin"
    version = "1.0.0"
    description = "按下键盘 Y 键时，暂停发送 20 秒，然后按需恢复。"

    def __init__(self):
        super().__init__()
        self.enabled: bool = True
        self._shortcut: Optional[QShortcut] = None
        self._was_sending: bool = False

    def activate(self, ctx):
        # Create a global shortcut on the main window to listen for 'Y'
        mw = getattr(ctx, "main_window", None)
        if mw is None or QShortcut is None or QKeySequence is None:
            return

        # Avoid creating duplicate shortcuts if re-activated
        if self._shortcut is None:
            self._shortcut = QShortcut(QKeySequence("Y"), mw)
            self._shortcut.setWhatsThis("按下 Y 暂停发送 20 秒")
            self._shortcut.activated.connect(lambda: self._on_y_pressed(mw))

    def deactivate(self):
        if self._shortcut is not None:
            try:
                self._shortcut.activated.disconnect()
            except Exception:
                pass
            try:
                # 销毁快捷键对象，避免反复启停后残留并继续拦截按键
                self._shortcut.setParent(None)
                self._shortcut.deleteLater()
            except Exception:
                pass
            self._shortcut = None

    # --- Internal handlers ---
    def _on_y_pressed(self, mw):
        if not self.enabled or mw is None:
            return

        # Detect current sending state and pause
        is_sending = getattr(mw, "is_sending", False)
        self._was_sending = bool(is_sending)

        # Stop sending immediately (safe even if already stopped)
        try:
            mw.stop_sending()
        except Exception:
            pass

        # Optional: provide UI feedback if status_label exists
        status_label = getattr(mw, "status_label", None)
        if status_label is not None:
            try:
                status_label.setText("已按下 Y：暂停发送 20 秒…")
            except Exception:
                pass

        # Resume after 20 seconds only if we were sending and still appropriate
        if QTimer is not None:
            QTimer.singleShot(20000, lambda: self._resume_if_needed(mw))

    def _resume_if_needed(self, mw):
        if not self.enabled or mw is None:
            return

        # If the user manually resumed during the pause, do nothing
        is_sending = getattr(mw, "is_sending", False)

        try_resume = self._was_sending and not is_sending
        self._was_sending = False

        if try_resume:
            try:
                mw.start_sending()
                status_label = getattr(mw, "status_label", None)
                if status_label is not None:
                    try:
                        status_label.setText("发送已自动恢复")
                    except Exception:
                        pass
            except Exception:
                pass


def plugin_entry():
    return PauseOnYPlugin()
