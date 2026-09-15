"""系统托盘与控制台：托盘菜单、恢复窗口、退出与控制台开关。"""

import logging
import sys

from PySide6.QtCore import QPropertyAnimation
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QStyle, QSystemTrayIcon


class TrayMixin:
    """系统托盘与控制台管理。"""

    # 显示/隐藏控制台窗口
    def on_toggle_console(self, enabled: bool):
        # 在 Windows 上切换控制台窗口的可见性；无控制台时可按需分配
        if sys.platform.startswith('win'):
            try:
                import ctypes as _ct
                hwnd = _ct.windll.kernel32.GetConsoleWindow()
                if enabled:
                    if not hwnd:
                        try:
                            _ct.windll.kernel32.AllocConsole()
                            hwnd = _ct.windll.kernel32.GetConsoleWindow()
                        except Exception:
                            pass
                    if hwnd:
                        _ct.windll.user32.ShowWindow(hwnd, 5)  # SW_SHOW
                        try:
                            _ct.windll.kernel32.SetConsoleOutputCP(65001)
                            _ct.windll.kernel32.SetConsoleCP(65001)
                        except Exception:
                            pass
                else:
                    if hwnd:
                        _ct.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
            except Exception as e:
                logging.error(f"Console visibility toggle failed: {e}")

    # 创建系统托盘图标与菜单
    def _setup_tray(self):
        # 在支持系统托盘的平台启用
        try:
            if not QSystemTrayIcon.isSystemTrayAvailable():
                return
        except Exception:
            pass

        icon = self.windowIcon()
        try:
            if icon.isNull():
                icon = self.style().standardIcon(QStyle.SP_ComputerIcon)
        except Exception:
            pass
        self.tray_icon = QSystemTrayIcon(icon, self)
        self.tray_icon.setToolTip("VRCOSC Pulse")

        self.tray_menu = QMenu()
        self.action_restore = QAction("打开/显示", self)
        self.action_toggle_send = QAction("▶ 开始发送", self)
        self.action_exit = QAction("退出", self)

        self.action_restore.triggered.connect(self._restore_from_tray)
        self.action_toggle_send.triggered.connect(self.on_toggle_send)
        self.action_exit.triggered.connect(self._on_exit_via_tray)

        self.tray_menu.addAction(self.action_restore)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(self.action_toggle_send)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(self.action_exit)
        self.tray_icon.setContextMenu(self.tray_menu)

        try:
            self.tray_icon.activated.connect(self._on_tray_activated)
        except Exception:
            pass
        self.tray_icon.show()
        self._update_tray_text()

    # 同步托盘菜单的开始/停止文案
    def _update_tray_text(self):
        try:
            if getattr(self, 'action_toggle_send', None):
                self.action_toggle_send.setText("⏹ 停止发送" if self.is_sending else "▶ 开始发送")
        except Exception:
            pass

    # 托盘图标点击：恢复窗口
    def _on_tray_activated(self, reason):
        try:
            if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
                self._restore_from_tray()
        except Exception:
            pass

    # 从托盘恢复窗口并播放淡入动画
    def _restore_from_tray(self):
        try:
            # 初始透明，显示后淡入并轻微回弹
            try:
                self.setWindowOpacity(0.0)
            except Exception:
                pass
            self.showNormal()
            self.activateWindow()
            self.raise_()
            try:
                anim = QPropertyAnimation(self, b"windowOpacity")
                anim.setDuration(200)
                anim.setKeyValueAt(0, 0.0)
                anim.setKeyValueAt(0.7, 1.0)
                anim.setKeyValueAt(0.85, 1.02)
                anim.setEndValue(1.0)
                # 保存引用，避免动画被垃圾回收
                self._restore_opacity_anim = anim
                anim.start()
            except Exception:
                # 失败则直接恢复不透明
                try:
                    self.setWindowOpacity(1.0)
                except Exception:
                    pass
        except Exception:
            pass

    # 托盘退出：关闭窗口
    def _on_exit_via_tray(self):
        try:
            self.close()
        except Exception:
            pass
