"""主窗口：组装各功能模块、处理窗口事件、管理设置持久化。"""

import ctypes
import logging
import sys
import threading
from typing import Optional

from PySide6.QtCore import Qt, QSize, QRectF, QTimer, QPropertyAnimation, QEvent, QEasingCurve, QParallelAnimationGroup, Signal
from PySide6.QtGui import QPixmap, QPainter, QColor, QPainterPath, QIcon
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QBoxLayout, QLabel, QPushButton, QSizePolicy, QSystemTrayIcon

from .core.osc import OSCClient
from .core.state import load_prefs, save_prefs
from .dialogs.settings import SettingsDialog
from .ui.background import BackgroundManager
from .ui.design import BRAND
from .ui.layout import UILayoutManager
from .mixins import DebugMixin, HistoryMixin, OscMixin, SendingMixin, ThemeMixin, TrayMixin, WallpaperMixin

logger = logging.getLogger(__name__)


class MainWindow(
    QMainWindow,
    WallpaperMixin,
    ThemeMixin,
    OscMixin,
    SendingMixin,
    HistoryMixin,
    DebugMixin,
    TrayMixin,
):
    """主窗口：组合各 mixin 提供完整功能。"""

    # 后台线程向主线程报告 OSC 探测结果（probe_id, enabled），确保 UI 更新线程安全
    oscProbeResult = Signal(int, bool)
    # 后台蓝牙扫描线程向主线程报告发现的设备列表
    chooseDeviceResult = Signal(list)

    # 主窗口初始化：加载偏好、创建 UI、启动定时器与托盘
    def __init__(self):
        super().__init__()
        self.setWindowTitle("VRCOSC Pulse")
        self.resize(1000, 680)

        # Global background wallpaper (system or custom)
        # Prefer loading real wallpaper at startup for better UX
        self.use_plain_background = False
        self.custom_wallpaper_path: Optional[str] = None
        self._user_plain_override = False
        self.wallpaper = self.load_wallpaper_for_current_size()
        # 初始化壁纸亮度信息
        self._wallpaper_is_light = False
        # 壁纸亮度因子（0=暗壁纸，1=亮壁纸）驱动次要文字与面板对比度
        self._wallpaper_light_factor: float = 0.0
        self._wallpaper_factor_anim: Optional[QPropertyAnimation] = None

        # 背景过渡管理器：负责淡入淡出与“模糊先出、清晰再进”
        try:
            self._bg_manager = BackgroundManager(self.wallpaper, parent=self)
            # 过渡帧推进时重绘窗口
            self._bg_manager.alphaChanged.connect(self.update)
        except Exception:
            self._bg_manager = None

        # 加载持久化偏好（壁纸 + 常规设置；控件就绪后再恢复）
        try:
            prefs = load_prefs()
            self._prefs = prefs if isinstance(prefs, dict) else {}
        except Exception:
            self._prefs = {}
        self.use_plain_background = bool(self._prefs.get('use_plain_background', False))
        path = self._prefs.get('custom_wallpaper_path')
        self.custom_wallpaper_path = path if path else None

        # Theme state
        self._theme_dark = self.is_system_dark_mode()
        # 强调色固定为品牌粉（见 ThemeMixin.apply_theme）。
        # 以前这里会调用 get_system_accent_color()，做一次 DWM 读取甚至壁纸取色，
        # 结果紧接着就被 apply_theme() 覆盖掉，纯属启动期的无谓开销。
        self._accent = QColor(BRAND)

        # 连接跨线程信号到主线程槽
        try:
            self.oscProbeResult.connect(self._on_osc_probe_result)
        except Exception as e:
            logger.debug(f"Connect oscProbeResult failed: {e}", exc_info=True)
        try:
            self.chooseDeviceResult.connect(self._on_device_scan_result)
        except Exception as e:
            logger.debug(f"Connect chooseDeviceResult failed: {e}", exc_info=True)

        # Header：品牌区 + 状态胶囊 + 设置
        from pathlib import Path as _P
        # BRAND 已在模块顶部导入；不要再在这里重复导入，否则整个 __init__ 内
        # 它是局部名，前面（主题状态初始化处）引用会 UnboundLocalError。
        from .ui.design import TEXT, TEXT_SECONDARY, SUCCESS, PILL_BG
        header = QWidget()
        header.setObjectName("appHeader")
        header.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        header.setFixedHeight(72)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 8, 20, 8)
        header_layout.setSpacing(12)

        # 品牌区：图标 + 标题/副标题，避免副标题从图标左侧开始。
        brand_row = QHBoxLayout()
        brand_row.setSpacing(12)
        brand_logo = QLabel()
        brand_logo.setObjectName("brandLogo")
        brand_logo.setFixedSize(38, 38)
        brand_logo.setAlignment(Qt.AlignCenter)
        logo_path = _P(__file__).resolve().parents[1] / "resources" / "icons" / "logo.svg"
        if logo_path.exists():
            logo_pix = QPixmap(str(logo_path))
            if not logo_pix.isNull():
                brand_logo.setPixmap(logo_pix.scaled(22, 22, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        brand_logo.setStyleSheet(f"background: {BRAND}; border-radius: 10px;")

        brand_text_col = QVBoxLayout()
        brand_text_col.setSpacing(1)
        self.title_label = QLabel("VRCOSC Pulse")
        self.title_label.setObjectName("appTitle")
        self.title_label.setStyleSheet(f"font-size: 23px; font-weight: 700; color: {TEXT};")
        self.subtitle_label = QLabel("让每一句话，都更有温度  ♡")
        self.subtitle_label.setStyleSheet(f"font-size: 12px; color: {TEXT_SECONDARY};")
        brand_text_col.addWidget(self.title_label)
        brand_text_col.addWidget(self.subtitle_label)
        brand_row.addWidget(brand_logo, 0, Qt.AlignVCenter)
        brand_row.addLayout(brand_text_col)
        brand_row.addStretch(1)

        # 状态胶囊：主状态 + 次状态，圆点颜色由 set_app_status() 统一更新。
        status_pill = QWidget()
        status_pill.setObjectName("headerStatusPill")
        status_pill.setFixedHeight(44)
        status_pill.setFixedWidth(138)
        sp_lay = QHBoxLayout(status_pill)
        sp_lay.setContentsMargins(13, 5, 13, 5)
        sp_lay.setSpacing(10)
        status_dot = QLabel()
        status_dot.setFixedSize(8, 8)
        status_dot.setStyleSheet(f"background: {SUCCESS}; border-radius: 4px;")
        status_text_col = QVBoxLayout()
        status_text_col.setSpacing(0)
        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet(f"font-size: 13px; font-weight: 700; color: {TEXT};")
        self.countdown_label = QLabel("一切正常")
        self.countdown_label.setStyleSheet(f"font-size: 10px; color: {TEXT_SECONDARY};")
        status_text_col.addWidget(self.status_label)
        status_text_col.addWidget(self.countdown_label)
        sp_lay.addWidget(status_dot)
        sp_lay.addLayout(status_text_col)
        status_pill.setStyleSheet(
            f"QWidget#headerStatusPill {{ background: {PILL_BG}; border-radius: 12px; }}"
        )
        self._header_status_dot = status_dot
        self._header_status_pill = status_pill
        self._brand_logo = brand_logo

        self.btn_open_settings = QPushButton("设置")
        self.btn_open_settings.setObjectName("secondaryBtn")
        self.btn_open_settings.setCursor(Qt.PointingHandCursor)
        self.btn_open_settings.setFixedSize(78, 40)
        try:
            icon_path = _P(__file__).resolve().parents[1] / "resources" / "icons" / "settings.svg"
            if icon_path.exists():
                self.btn_open_settings.setIcon(QIcon(str(icon_path)))
                self.btn_open_settings.setIconSize(QSize(16, 16))
        except Exception:
            pass
        self.btn_open_settings.clicked.connect(self.open_settings_dialog)

        header_layout.addLayout(brand_row, 1)
        header_layout.addWidget(status_pill)
        header_layout.addWidget(self.btn_open_settings)

        # Body 采用 UILayoutManager 统一创建与管理
        try:
            self._layout_mgr = UILayoutManager(self)
            # 创建主体（输入/历史/工具），并自动嵌入调试面板与设置页
            self._layout_mgr.setup_body_layout()
        except Exception:
            # 回退：如果布局管理器失败，保持最小影响（抛出以便日志记录）
            raise

        # Assemble
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(header)
        # 直接添加由布局管理器创建的主体容器
        try:
            root_layout.addWidget(self.body_widget, 1)
        except Exception:
            # 如果 body_widget 未暴露，则兼容使用布局管理器内部引用
            root_layout.addWidget(self._layout_mgr.body_widget, 1)
        self.setCentralWidget(root)

        # 连接必要信号（组件中不做业务绑定）
        try:
            self.input_edit.textChanged.connect(self.on_text_changed)
        except Exception:
            pass

        # Attach animated scrollbars (fixed 10px track, 6->8px handle with 80ms easing)
        try:
            from app.ui.widgets import BreathingScrollBar  # type: ignore
        except Exception:
            BreathingScrollBar = None  # type: ignore
        try:
            if BreathingScrollBar is not None:
                sb1 = BreathingScrollBar(Qt.Vertical, self.input_edit)
                sb2 = BreathingScrollBar(Qt.Vertical, self.history_edit)
                # Sync theme
                dark = bool(getattr(self, '_theme_dark', True))
                sb1.set_dark_mode(dark); sb2.set_dark_mode(dark)
                self.input_edit.setVerticalScrollBar(sb1)
                self.history_edit.setVerticalScrollBar(sb2)
        except Exception:
            pass

        # 初始壁纸亮度与背景更新
        try:
            self._update_wallpaper_luminance()
        except Exception:
            pass
        self.input_panel.update_background()
        self.history_panel.update_background()
        self.tool_panel.update_background()

        # 先初始化运行状态，再应用主题/恢复偏好。尤其 auto_hr=True 时，
        # 恢复勾选会立即启动 BLE 监测，不能在后面把引用重新置空。
        self.is_sending = False
        self._send_lock = threading.Lock()
        self._toggle_pending = False
        # OSC 探测序号与“允许弹窗”的探测序号（防止并发探测互相消费弹窗令牌）
        self._osc_probe_seq = 0
        self._osc_popup_probe_id = None
        self.hr_monitor = None

        self.apply_theme()
        self.theme_dark = self.is_system_dark_mode()

        # 恢复持久化的常规设置（勾选项、间隔、外观/性能），并连接自动保存
        self._apply_saved_ui_settings()
        self._connect_settings_signals()

        self.max_message_length = 144
        self._current_blur_strength = int(self._prefs.get('blur_strength', 14))
        self._current_white_alpha = int(self._prefs.get('white_alpha', 28))
        self._current_corner_radius = int(self._prefs.get('corner_radius', 16))

        # Initialize OSC client via local wrapper
        self.osc_client = OSCClient("127.0.0.1", 9000)
        try:
            self._probe_osc_async()
        except Exception:
            pass

        self.send_timer = QTimer(self)
        self.theme_timer = QTimer(self)
        self.theme_timer.setInterval(5_000)
        self.theme_timer.timeout.connect(self.on_theme_tick)
        self.theme_timer.start()
        self.send_timer.setInterval(self.spin_interval.value() * 1000)
        self.send_timer.timeout.connect(self.on_send_timer)
        self.countdown_timer = QTimer(self)
        self.countdown_timer.setInterval(1000)
        self.countdown_timer.timeout.connect(self.on_countdown_tick)
        self._countdown_seconds = 0
        self.debug_timer = QTimer(self)
        self.debug_timer.setInterval(1000)
        self.debug_timer.timeout.connect(self.update_debug_info)
        self.debug_timer.start()

        # 系统托盘图标与菜单
        try:
            self._setup_tray()
        except Exception:
            pass

        # 启动时按持久化的「显示控制台」偏好决定控制台可见性
        try:
            if sys.platform.startswith('win'):
                import ctypes as _ct
                show_console = bool(
                    getattr(self, "console_toggle", None) and self.console_toggle.isChecked()
                )
                hwnd = _ct.windll.kernel32.GetConsoleWindow()
                if hwnd:
                    _ct.windll.user32.ShowWindow(hwnd, 5 if show_console else 0)  # SW_SHOW / SW_HIDE
        except Exception:
            pass

        # Debounced resize handler to avoid heavy work on every event
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._deferred_resize)

        self.start_btn.clicked.connect(self.on_toggle_send)

        self.set_performance_mode(self.performance_mode)
        self.set_static_blur_enabled(self.static_blur)

        # 已移除 _default_blurs（per-panel 24/18/12/6）：启动时它会覆盖
        # set_performance_mode() 刚恢复的用户模糊值，使设置与渲染不一致。
        # 外观现在统一由 _current_blur_strength 驱动。

        # Apply initial wallpaper immediately to avoid startup white/black screen
        try:
            self._apply_initial_wallpaper()
        except Exception:
            pass

        # Subtle fade-in to smooth the transition
        try:
            self.setWindowOpacity(0.0)
            self._fade_in_anim = QPropertyAnimation(self, b"windowOpacity")
            self._fade_in_anim.setDuration(250)
            self._fade_in_anim.setStartValue(0.0)
            self._fade_in_anim.setEndValue(1.0)
            self._fade_in_anim.start()
        except Exception:
            pass

    def set_app_status(self, title: str, detail: str | None = None, level: str = "normal") -> None:
        """统一更新顶部状态胶囊，避免业务代码直接拼很长的状态文本。"""
        try:
            from .ui.design import BRAND, SUCCESS, WARN, TEXT_MUTED
            colors = {
                "normal": SUCCESS,
                "success": SUCCESS,
                "info": BRAND,
                "warning": WARN,
                "error": WARN,
                "muted": TEXT_MUTED,
            }
            raw_title = str(title)
            shown_title = raw_title if len(raw_title) <= 10 else raw_title[:9] + "…"
            self.status_label.setText(shown_title)
            self.status_label.setToolTip(raw_title if raw_title != shown_title else "")
            if detail is not None:
                raw_detail = str(detail)
                shown_detail = raw_detail if len(raw_detail) <= 16 else raw_detail[:15] + "…"
                self.countdown_label.setText(shown_detail)
                self.countdown_label.setToolTip(raw_detail if raw_detail != shown_detail else "")
            elif not bool(getattr(self, "is_sending", False)):
                self.countdown_label.setText("一切正常")
                self.countdown_label.setToolTip("")
            dot = getattr(self, "_header_status_dot", None)
            if dot is not None:
                color = colors.get(level, SUCCESS)
                dot.setStyleSheet(f"background: {color}; border-radius: 4px;")
        except Exception:
            # 顶部状态失败不应影响核心发送流程。
            try:
                self.status_label.setText(title)
            except Exception:
                pass

    # 启动时把持久化设置恢复到各控件
    def _apply_saved_ui_settings(self) -> None:
        """启动时把持久化的常规设置恢复到已创建的控件上。"""
        prefs = getattr(self, '_prefs', {})
        for name, default in (
            ('auto_wrap', False),
            ('auto_time', False),
            ('auto_window', False),
            ('auto_music', False),
            ('auto_idle', False),
            ('auto_hr', False),
            ('auto_hardware', False),
            ('auto_cpu', False),
            ('auto_ram', False),
            ('auto_gpu', False),
            ('auto_temp', False),
        ):
            cb = getattr(self, name, None)
            if cb is not None:
                try:
                    cb.setChecked(bool(prefs.get(name, default)))
                except Exception:
                    pass
        try:
            self.spin_interval.setValue(int(prefs.get('spin_interval', 30)))
        except Exception:
            pass
        try:
            # 不屏蔽信号：若保存了“显示控制台”，启动时恢复可见状态
            self.console_toggle.setChecked(bool(prefs.get('console_toggle', False)))
        except Exception:
            pass
        self._acrylic_enabled = bool(prefs.get('acrylic_enabled', True))
        self._shadow_enabled = bool(prefs.get('shadow_enabled', True))
        self.static_blur = bool(prefs.get('static_blur', False))
        self.performance_mode = bool(prefs.get('performance_mode', True))

    # 连接设置控件的自动保存信号
    def _connect_settings_signals(self) -> None:
        """把设置控件的变化接到统一保存。"""
        for name in (
            'auto_wrap', 'auto_time', 'auto_window', 'auto_music', 'auto_idle', 'auto_hr',
            'auto_hardware', 'auto_cpu', 'auto_ram', 'auto_gpu', 'auto_temp', 'console_toggle',
        ):
            cb = getattr(self, name, None)
            if cb is not None:
                try:
                    cb.toggled.connect(self._save_settings)
                except Exception:
                    pass
        try:
            # 走 on_interval_changed：既持久化，也把新周期同步给 send_timer
            self.spin_interval.valueChanged.connect(self.on_interval_changed)
        except Exception:
            pass

    # 汇总所有设置写入偏好文件
    def _save_settings(self) -> None:
        """汇总所有可持久化设置并写入偏好文件。"""
        try:
            prefs = {
                'use_plain_background': bool(self.use_plain_background),
                'custom_wallpaper_path': self.custom_wallpaper_path or "",
                'auto_wrap': self.auto_wrap.isChecked(),
                'auto_time': self.auto_time.isChecked(),
                'auto_window': self.auto_window.isChecked(),
                'auto_music': self.auto_music.isChecked(),
                'auto_idle': self.auto_idle.isChecked(),
                'auto_hr': self.auto_hr.isChecked(),
                'auto_hardware': self.auto_hardware.isChecked(),
                'auto_cpu': self.auto_cpu.isChecked(),
                'auto_ram': self.auto_ram.isChecked(),
                'auto_gpu': self.auto_gpu.isChecked(),
                'auto_temp': self.auto_temp.isChecked(),
                'console_toggle': self.console_toggle.isChecked(),
                'spin_interval': self.spin_interval.value(),
                'performance_mode': bool(self.performance_mode),
                'static_blur': bool(self.static_blur),
                'blur_strength': int(self._current_blur_strength),
                'white_alpha': int(self._current_white_alpha),
                'corner_radius': int(self._current_corner_radius),
                'acrylic_enabled': bool(getattr(self, '_acrylic_enabled', True)),
                'shadow_enabled': bool(getattr(self, '_shadow_enabled', True)),
            }
            pm = getattr(self, 'plugin_manager', None)
            if pm is not None:
                prefs['plugins_enabled'] = [
                    str(getattr(p, 'name', ''))
                    for p in pm.plugins
                    if getattr(p, 'enabled', False)
                ]
            else:
                # 启动阶段 plugin_manager 尚未挂载：绝不能丢掉磁盘上的启用列表，
                # 否则每次启动都会把 plugins_enabled 抹掉，插件永远无法保持启用。
                prefs['plugins_enabled'] = list(
                    getattr(self, '_prefs', {}).get('plugins_enabled', []) or []
                )
            # 与磁盘上的旧内容合并，避免固定字典写盘时丢掉其它字段
            try:
                existing = load_prefs()
            except Exception:
                existing = {}
            if isinstance(existing, dict):
                existing.update(prefs)
                prefs = existing
            save_prefs(prefs)
        except Exception:
            logger.warning("Failed to save settings", exc_info=True)

    # 按保存的启用列表恢复插件
    def _restore_plugins_from_prefs(self) -> None:
        """按保存的启用列表恢复插件；依赖未就绪的重试，最终失败记日志。"""
        pm = getattr(self, 'plugin_manager', None)
        if pm is None:
            return
        names = getattr(self, '_prefs', {}).get('plugins_enabled', []) or []
        remaining = [str(n) for n in names]
        while remaining:
            progressed = False
            errors: dict[str, str] = {}
            for name in list(remaining):
                ok, msg = pm.set_plugin_enabled(name, True)
                if ok:
                    remaining.remove(name)
                    progressed = True
                else:
                    errors[name] = msg
            if not progressed:
                for name, msg in errors.items():
                    logger.warning("Plugin '%s' not restored from saved settings: %s", name, msg)
                break

    # 窗口尺寸变化：延迟触发重排与壁纸刷新
    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Debounce heavy operations; run after 200ms of inactivity
        try:
            self._resize_timer.start(200)
        except Exception:
            # Fallback: run immediately if timer fails
            self._deferred_resize()

    # 防抖后的尺寸处理：更新壁纸、面板与布局方向
    def _deferred_resize(self):
        # Recompute wallpaper and update acrylic panels
        try:
            self.wallpaper = self.load_wallpaper_for_current_size()
            try:
                if getattr(self, '_bg_manager', None):
                    # 窗口尺寸变化时直接更新当前壁纸，不做过渡动画
                    self._bg_manager.set_current(self.wallpaper)
            except Exception:
                pass
            try:
                self._update_wallpaper_luminance()
            except Exception:
                pass
            self.input_panel.wallpaper = self.wallpaper
            self.history_panel.wallpaper = self.wallpaper
            self.tool_panel.wallpaper = self.wallpaper
            try:
                # 同步调试面板的壁纸，避免在resize后仍保留旧的系统壁纸切片
                self.debug_panel.wallpaper = self.wallpaper
            except Exception:
                pass
            self.input_panel.update_background()
            self.history_panel.update_background()
            self.tool_panel.update_background()
            self.debug_panel.update_background()
            # 壁纸改变后，重新应用主题以刷新次要文字对比度
            try:
                self.apply_theme()
            except Exception:
                pass
        except Exception:
            pass

        # Switch layout direction based on width
        try:
            if self.width() < 1000:
                self.body.setDirection(QBoxLayout.TopToBottom)
            else:
                self.body.setDirection(QBoxLayout.LeftToRight)
        except Exception:
            pass

        try:
            self.update()
        except Exception:
            pass

    # 绘制壁纸背景、顶部渐变与内侧柔光阴影
    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.wallpaper.isNull():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            rect = self.rect()
            # 外框圆角：常规 10px，最大化时收回到 0 以避免锯齿
            outer_radius = 10
            try:
                if self.isMaximized():
                    outer_radius = 0
            except Exception:
                pass
            path = QPainterPath()
            path.addRoundedRect(QRectF(rect.adjusted(0, 0, -1, -1)), outer_radius, outer_radius)
            painter.setClipPath(path)
            try:
                if getattr(self, '_bg_manager', None):
                    self._bg_manager.render_into(painter, rect)
                else:
                    painter.drawPixmap(0, 0, self.wallpaper)
            except Exception:
                painter.drawPixmap(0, 0, self.wallpaper)
            # Overlay top gradient (40% height) to improve legibility
            from PySide6.QtGui import QLinearGradient
            h = rect.height()
            grad = QLinearGradient(0, 0, 0, h)
            alpha = 80 if self._theme_dark else 40
            grad.setColorAt(0.0, QColor(0, 0, 0, 0))
            grad.setColorAt(0.4, QColor(0, 0, 0, alpha))
            painter.fillRect(rect, grad)

            # 柔光阴影：2px 线宽，24px 模糊，8% 不透明度
            try:
                # 在单独图层上绘制黑色细边并模糊，得到柔和的内侧阴影效果
                from PySide6.QtGui import QPen
                try:
                    from utils.blur import blur_pixmap as _blur_pixmap
                except Exception:
                    _blur_pixmap = None  # type: ignore

                if _blur_pixmap is not None:
                    layer = QPixmap(rect.size())
                    layer.fill(Qt.transparent)
                    lp = QPainter(layer)
                    lp.setRenderHint(QPainter.Antialiasing, True)
                    pen = QPen(QColor(0, 0, 0, int(0.08 * 255)))
                    pen.setWidth(2)
                    lp.setPen(pen)
                    lp.setBrush(Qt.NoBrush)
                    lp.drawRoundedRect(QRectF(rect.adjusted(1, 1, -2, -2)), outer_radius, outer_radius)
                    lp.end()
                    blurred = _blur_pixmap(layer, 24)
                    painter.drawPixmap(0, 0, blurred)
            except Exception:
                pass
            painter.end()

    # 安全停止并释放 Qt 对象
    def _safe_stop_delete(self, obj, name: str) -> None:
        """安全停止并删除 Qt 对象，避免在关闭时抛出未捕获异常。

        - 优先调用 `stop()`（若存在）
        - 再调用 `deleteLater()`（若存在）
        - 所有异常均记录到日志，便于后续诊断
        """
        if not obj:
            return
        try:
            stop = getattr(obj, 'stop', None)
            if callable(stop):
                stop()
        except Exception as e:
            logger.warning(f"Stop failed for {name}: {e}", exc_info=True)
        try:
            delete_later = getattr(obj, 'deleteLater', None)
            if callable(delete_later):
                delete_later()
        except Exception as e:
            logger.warning(f"deleteLater failed for {name}: {e}", exc_info=True)

    # 关闭窗口：停止定时器与后台服务
    def closeEvent(self, event):
        # 真实退出路径：清理所有定时器与后台服务
        try:
            if hasattr(self, 'send_timer') and isinstance(self.send_timer, QTimer):
                self.send_timer.stop()
        except Exception as e:
            logger.debug(f"Failed stopping send_timer: {e}", exc_info=True)
        try:
            if hasattr(self, 'theme_timer') and isinstance(self.theme_timer, QTimer):
                self.theme_timer.stop()
        except Exception as e:
            logger.debug(f"Failed stopping theme_timer: {e}", exc_info=True)
        try:
            if hasattr(self, 'countdown_timer') and isinstance(self.countdown_timer, QTimer):
                self.countdown_timer.stop()
        except Exception as e:
            logger.debug(f"Failed stopping countdown_timer: {e}", exc_info=True)

        # 清理动画资源，避免退出时残留对象（带日志）
        self._safe_stop_delete(getattr(self, 'hr_dot_anim', None), 'hr_dot_anim')
        self._safe_stop_delete(getattr(self, '_fade_in_anim', None), '_fade_in_anim')
        self._safe_stop_delete(getattr(self, '_wallpaper_factor_anim', None), '_wallpaper_factor_anim')
        self._safe_stop_delete(getattr(self, '_corner_radius_anim', None), '_corner_radius_anim')

        try:
            if hasattr(self, 'debug_timer') and isinstance(self.debug_timer, QTimer):
                self.debug_timer.stop()
        except Exception as e:
            logger.debug(f"Failed stopping debug_timer: {e}", exc_info=True)
        try:
            if getattr(self, 'hr_monitor', None):
                self.hr_monitor.stop()
        except Exception as e:
            logger.warning(f"Failed to stop hr_monitor on close: {e}", exc_info=True)
        event.accept()

    # 窗口状态变化：最小化到托盘、最大化圆角动画
    def changeEvent(self, event):
        try:
            super().changeEvent(event)
        except Exception:
            pass
        try:
            if event and event.type() == QEvent.WindowStateChange:
                if self.isMinimized():
                    self.hide()
                    if getattr(self, 'tray_icon', None):
                        try:
                            self.tray_icon.show()
                            self.tray_icon.showMessage("VRCOSC Pulse", "已最小化到系统托盘", QSystemTrayIcon.Information, 2000)
                        except Exception:
                            pass
                # Win11 风格：最大化/恢复时以 80ms 动画收放圆角
                try:
                    prev_state = int(getattr(event, 'oldState', lambda: int(self.windowState()))())
                except Exception:
                    prev_state = int(self.windowState())
                new_maximized = bool(self.windowState() & Qt.WindowMaximized)
                old_maximized = bool(prev_state & Qt.WindowMaximized)
                if new_maximized and not old_maximized:
                    # 正在最大化：当前圆角 -> 0
                    try:
                        self._animate_panels_corner_radius(int(self._current_corner_radius), 0, 80)
                    except Exception:
                        pass
                elif (not new_maximized) and old_maximized:
                    # 正在恢复：0 -> 当前圆角
                    try:
                        self._animate_panels_corner_radius(0, int(self._current_corner_radius), 80)
                    except Exception:
                        pass
        except Exception:
            pass

    # 面板圆角批量动画
    def _animate_panels_corner_radius(self, start: int, end: int, duration_ms: int = 80):
        try:
            # 停止上一轮动画（若存在）
            if hasattr(self, '_corner_radius_anim') and self._corner_radius_anim is not None:
                try:
                    self._corner_radius_anim.stop()
                    # 删除上一组动画以避免资源累积
                    self._corner_radius_anim.deleteLater()
                except Exception:
                    pass
            group = QParallelAnimationGroup(self)
            for panel in (self.input_panel, self.history_panel, self.tool_panel, self.debug_panel):
                try:
                    # 将动画的父对象设为组，便于统一释放
                    anim = QPropertyAnimation(panel, b"cornerRadius", group)
                    anim.setDuration(int(duration_ms))
                    anim.setStartValue(int(start))
                    anim.setEndValue(int(end))
                    anim.setEasingCurve(QEasingCurve.OutCubic)
                    group.addAnimation(anim)
                except Exception:
                    pass
            self._corner_radius_anim = group
            group.start()
        except Exception:
            # 兜底：直接设置终值
            try:
                for panel in (self.input_panel, self.history_panel, self.tool_panel, self.debug_panel):
                    panel.set_params(corner_radius=int(end))
            except Exception:
                pass

    # 打开设置对话框
    def open_settings_dialog(self):
        """打开设置对话框。

        每次 open 都新建一个对话框（保证页面数据是最新的），但必须设置
        `WA_DeleteOnClose` 并在关闭后释放引用：带 parent 的 QDialog 不会因为
        Python 引用消失而销毁，否则每次打开都会残留一个完整对话框（页面、滑条、
        插件开关的信号连接）直到进程退出。
        """
        prev = getattr(self, '_settings_dialog', None)
        if prev is not None:
            try:
                prev.close()
                prev.deleteLater()
            except Exception:
                pass
            self._settings_dialog = None

        dlg = SettingsDialog(self)
        self._settings_dialog = dlg
        try:
            dlg.setAttribute(Qt.WA_DeleteOnClose, True)
        except Exception:
            pass
        try:
            dlg.exec()
        finally:
            if getattr(self, '_settings_dialog', None) is dlg:
                self._settings_dialog = None
            try:
                dlg.deleteLater()
            except Exception:
                pass
