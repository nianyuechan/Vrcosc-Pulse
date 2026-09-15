"""主题与外观：系统深浅色/强调色读取、样式应用、按钮动效与模糊/阴影参数。"""

import ctypes
import logging
import os

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRect
from PySide6.QtGui import QColor, QCursor, QIcon
from PySide6.QtWidgets import QPushButton, QSizePolicy

from ..ui.panels import UiTokens
from ..ui.widgets import QRippleWidget
from ..ui.design import (
    BRAND, BRAND_HOVER, BRAND_PRESSED, BRAND_SOFT, BRAND_SOFT_2,
    TEXT, TEXT_SECONDARY, TEXT_MUTED, BORDER, PILL_BG, DARK_PILL, TRACK, SUCCESS, rgba,
)


class ThemeMixin:
    """主题、样式与界面动效。"""

    def get_secondary_grey(self) -> str:
        """次要文字颜色：深色主题用浅灰，浅色主题/浅壁纸用深灰，保证可读。"""
        dark = bool(getattr(self, "_theme_dark", True))
        try:
            factor = float(getattr(self, "_wallpaper_light_factor", 0.0))
        except Exception:
            factor = 1.0 if getattr(self, "_wallpaper_is_light", False) else 0.0
        t = 0.0 if factor < 0.0 else 1.0 if factor > 1.0 else factor
        if dark:
            # 深色 UI：次要文字偏亮；浅壁纸时略降，避免与乳白遮罩同化
            v = int(round(170 * (1.0 - t) + 150 * t))
        else:
            # 浅色 UI：次要文字偏深；浅壁纸时更深
            v = int(round(110 * (1.0 - t) + 72 * t))
        hv = f"{max(0, min(255, v)):02X}"
        return f"#{hv}{hv}{hv}"

    def _panel_contrast_overrides(self) -> dict:
        """按系统主题 + 壁纸亮度返回面板 white/scrim 参数。"""
        dark = bool(getattr(self, "_theme_dark", True))
        try:
            factor = float(getattr(self, "_wallpaper_light_factor", 0.0))
        except Exception:
            factor = 1.0 if getattr(self, "_wallpaper_is_light", False) else 0.0
        t = 0.0 if factor < 0.0 else 1.0 if factor > 1.0 else factor
        if dark:
            # 深色 UI：浅壁纸时加暗遮罩，保住白字对比
            scrim = int(round(0 + 70 * t))
            white = int(round(20 - 10 * t))
            return {
                "input": {"white_alpha": max(white, 10), "scrim_alpha": scrim},
                "history": {"white_alpha": max(white - 8, 4), "scrim_alpha": scrim},
                "tool": {"white_alpha": max(white - 8, 4), "scrim_alpha": scrim},
                "debug": {"white_alpha": max(white - 12, 0), "scrim_alpha": int(scrim * 1.1)},
            }
        # 浅色 UI：浅壁纸时提高乳白磨砂，衬托深色文字
        base = int(round(8 + 42 * t))
        return {
            "input": {"white_alpha": base + 8, "scrim_alpha": 0},
            "history": {"white_alpha": base, "scrim_alpha": 0},
            "tool": {"white_alpha": base, "scrim_alpha": 0},
            "debug": {"white_alpha": max(base - 6, 0), "scrim_alpha": 0},
        }

    def _apply_panel_contrast(self) -> None:
        """把对比度参数落到四个亚克力面板。"""
        try:
            overrides = self._panel_contrast_overrides()
            dark = bool(getattr(self, "_theme_dark", True))
            perf = bool(getattr(self, "performance_mode", False))
            for key, panel_name in (
                ("input", "input_panel"),
                ("history", "history_panel"),
                ("tool", "tool_panel"),
                ("debug", "debug_panel"),
            ):
                panel = getattr(self, panel_name, None)
                if panel is None:
                    continue
                params = overrides[key]
                white = int(params["white_alpha"])
                scrim = int(params["scrim_alpha"])
                if perf:
                    # 性能模式仍保留最低可读性遮罩，避免浅壁纸文字发灰
                    white = min(white, 22) if white > 0 else 0
                    # 深色 UI 的暗遮罩对性能几乎无影响，完整保留
                if dark:
                    border_color = QColor(255, 255, 255)
                    border_alpha = 34
                    shadow_alpha = 54
                else:
                    border_color = QColor(BORDER)
                    border_alpha = 175
                    shadow_alpha = 10
                panel.set_params(
                    white_alpha=white,
                    scrim_alpha=scrim,
                    border_color=border_color,
                    border_alpha=border_alpha,
                )
                panel.set_shadow_params(blur=12, offset_y=1, alpha=shadow_alpha)
        except Exception:
            pass

    # 按名称获取应用图标（系统主题 -> 本地资源）
    def get_icon(self, name: str) -> QIcon:
        """优先使用应用内 SVG，保证不同 Windows 主题下图标风格一致。"""
        base = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'resources', 'icons', f'{name}.svg',
        )
        if os.path.exists(base):
            return QIcon(base)

        theme_map = {
            'settings': ['preferences-system', 'emblem-system', 'settings'],
            'play': ['media-playback-start', 'play'],
            'trash': ['user-trash', 'edit-delete', 'trash'],
            'image': ['image-x-generic', 'insert-image', 'image'],
            'monitor': ['computer', 'video-display', 'monitor'],
            'refresh': ['view-refresh', 'reload', 'refresh'],
        }
        for key in theme_map.get(name, [name]):
            icon = QIcon.fromTheme(key)
            if not icon.isNull():
                return icon
        return QIcon()

    # 定时检测系统深浅色变化并应用主题
    def on_theme_tick(self):
        try:
            current = self.is_system_dark_mode()
        except Exception:
            current = self.theme_dark
        if current != getattr(self, 'theme_dark', current):
            self._theme_dark = current
            self.theme_dark = current
            self.apply_theme()
            # 同步滚动条的暗色/亮色配色
            try:
                for sb in (self.input_edit.verticalScrollBar(), self.history_edit.verticalScrollBar()):
                    if hasattr(sb, 'set_dark_mode'):
                        sb.set_dark_mode(self.theme_dark)
            except Exception:
                pass

    # 读取 Windows 深色模式开关
    def is_system_dark_mode(self) -> bool:
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
                val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                return int(val) == 0
        except Exception:
            return True

    # 读取系统强调色；系统色为白色/极浅时尝试从壁纸提取强调色兜底。
    # 注意：应用当前固定使用品牌粉（见 apply_theme），这两个读取接口暂未接入，
    # 保留是为了将来做“跟随系统强调色”的可选项，不要在启动路径上调用。
    def get_system_accent_color(self) -> QColor:
        accent = self._read_system_accent_color()
        try:
            hsv = accent.toHsv()
            if hsv.saturationF() < 0.2 and hsv.valueF() > 0.85:
                extract = getattr(self, "extract_accent_color_from_wallpaper", None)
                if callable(extract):
                    from_wallpaper = extract()
                    if from_wallpaper is not None:
                        return from_wallpaper
        except Exception:
            pass
        return accent

    # 读取 Windows 系统强调色（DWM / 注册表）
    def _read_system_accent_color(self) -> QColor:
        try:
            dwmapi = ctypes.windll.dwmapi
            color = ctypes.c_uint()
            opaque = ctypes.c_int()
            res = dwmapi.DwmGetColorizationColor(ctypes.byref(color), ctypes.byref(opaque))
            if res == 0:
                d = int(color.value)
                a = (d >> 24) & 0xFF
                r = (d >> 16) & 0xFF
                g = (d >> 8) & 0xFF
                b = d & 0xFF
                return QColor(r, g, b, a if a > 0 else 255)
        except Exception:
            pass
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\DWM") as key:
                val, _ = winreg.QueryValueEx(key, "ColorizationColor")
                d = int(val)
                a = (d >> 24) & 0xFF
                r = (d >> 16) & 0xFF
                g = (d >> 8) & 0xFF
                b = d & 0xFF
                return QColor(r, g, b, a if a > 0 else 255)
        except Exception:
            pass
        return QColor(0, 120, 215)

    # 应用整套配色与控件样式
    def apply_theme(self):
        dark = self._theme_dark
        # 品牌粉固定强调，不随系统强调色漂移
        try:
            self._accent = QColor(BRAND)
        except Exception:
            pass
        text = "#F2F4F8" if dark else TEXT
        secondary = self.get_secondary_grey()
        accent = BRAND
        accent_bg_dark = rgba(BRAND, 0.28) if dark else BRAND_SOFT
        accent_border = rgba(BRAND, 0.55) if dark else rgba(BRAND, 0.35)
        accent_handle = rgba(BRAND, 0.60)

        panel_bg = "rgba(255,255,255,6)" if dark else "rgba(0,0,0,4)"
        panel_border = "rgba(255,255,255,12)" if dark else BORDER
        pill_bg = DARK_PILL if dark else PILL_BG
        track_bg = "rgba(255,255,255,0.12)" if dark else TRACK
        badge_bg = rgba(BRAND, 0.16) if dark else BRAND_SOFT

        font_family = "'Segoe UI Variable', 'Microsoft YaHei UI', 'Microsoft YaHei', 'PingFang SC', sans-serif"
        try:
            self.setStyleSheet(f"""
                QLabel, QPushButton, QTextEdit, QCheckBox, QSpinBox, QSlider {{
                    font-family: {font_family};
                    font-size: 14px;
                }}
            """)
        except Exception as ex:
            logging.warning("Failed to apply scoped stylesheet: %s", ex)

        # 顶栏
        try:
            self.title_label.setStyleSheet(f"font-size: 23px; font-weight: 700; color: {text};")
            if getattr(self, "subtitle_label", None):
                self.subtitle_label.setStyleSheet(f"font-size: 12px; color: {secondary};")
            status_pill = getattr(self, "_header_status_pill", None)
            if status_pill is not None:
                status_pill.setStyleSheet(
                    f"QWidget#headerStatusPill {{ background: {pill_bg}; border-radius: 12px; }}"
                )
        except Exception:
            pass

        # 四张卡片的标题图标底统一跟随深浅色。
        for name in ("input_title_icon", "history_title_icon", "tool_title_icon", "debug_title_icon"):
            badge = getattr(self, name, None)
            if badge is not None:
                try:
                    badge.setStyleSheet(f"background: {badge_bg}; border-radius: 9px;")
                except Exception:
                    pass

        # 卡片标题
        for attr in ("in_title", "hist_title", "tool_title"):
            lbl = getattr(self, attr, None)
            if lbl is not None:
                lbl.setStyleSheet(f"color: {text}; font-size: 19px; font-weight: 700;")
        dbg_title = getattr(self, "dbg_title", None)
        if dbg_title is not None:
            dbg_title.setStyleSheet(f"color: {text}; font-size: 19px; font-weight: 700;")

        # 主按钮
        self.start_btn.setStyleSheet(f"""
            QPushButton {{
                background: {BRAND};
                color: white;
                font-weight: 600;
                font-size: 15px;
                border: none;
                border-radius: 10px;
                padding: 12px 18px;
            }}
            QPushButton:hover:enabled {{ background: {BRAND_HOVER}; }}
            QPushButton:pressed:enabled {{ background: {BRAND_PRESSED}; }}
            QPushButton:disabled {{
                background: {"#FADDE6" if not dark else rgba(BRAND, 0.22)};
                color: {"#C25F7F" if not dark else secondary};
                border: 1px solid {"#F2C3D1" if not dark else rgba(BRAND, 0.18)};
            }}
        """)
        try:
            self.start_btn.setEnabled(bool(self.input_edit.toPlainText().strip()) or bool(self.is_sending))
        except Exception:
            pass

        # 次按钮 / 幽灵按钮
        ghost = f"""
            QPushButton {{ background: transparent; color: {secondary}; border: none;
                border-radius: 8px; padding: 4px 10px; font-size: 13px; }}
            QPushButton:hover {{ background: {BRAND_SOFT if not dark else rgba(BRAND, 0.15)}; color: {BRAND}; }}
        """
        secondary_btn = f"""
            QPushButton {{ background: {BRAND_SOFT if not dark else rgba(BRAND, 0.18)};
                color: {BRAND}; border: 1px solid {accent_border};
                border-radius: 9px; padding: 6px 14px; font-size: 13px; font-weight: 600; }}
            QPushButton:hover {{ background: {BRAND_SOFT_2 if not dark else rgba(BRAND, 0.28)}; }}
            QPushButton:disabled {{ color: {TEXT_MUTED if not dark else secondary}; background: {pill_bg}; border-color: transparent; }}
        """
        try:
            settings_btn = f"""
                QPushButton {{
                    background: {"rgba(255,255,255,0.72)" if not dark else DARK_PILL};
                    color: {text};
                    border: 1px solid {BORDER if not dark else "rgba(255,255,255,0.15)"};
                    border-radius: 10px;
                    padding: 6px 12px;
                    font-size: 13px;
                    font-weight: 600;
                }}
                QPushButton:hover {{
                    background: {BRAND_SOFT if not dark else rgba(BRAND, 0.15)};
                    color: {BRAND};
                    border-color: {rgba(BRAND, 0.35)};
                }}
            """
            self.btn_open_settings.setStyleSheet(settings_btn)
        except Exception:
            pass
        for name in ("clear_input_btn", "clear_history_btn"):
            btn = getattr(self, name, None)
            if btn is not None:
                btn.setStyleSheet(ghost)
        choose = getattr(self, "choose_hr_btn", None)
        if choose is not None:
            choose.setStyleSheet(secondary_btn)

        # 分组标题：整行粉条，与右侧 dashboard 分区一致
        try:
            for t in (getattr(self, 'tool_group_titles', None) or []):
                t.setFixedHeight(40)
                t.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                t.setStyleSheet(
                    f"""
                    QWidget#toolGroupTitle {{
                        background-color: {"#FFF0F4" if not dark else rgba(BRAND, 0.16)};
                        border: none;
                        border-radius: 9px;
                    }}
                    QLabel#toolGroupTitleText {{
                        color: {"#F25582" if not dark else BRAND};
                        font-size: 13px;
                        font-weight: 600;
                        background: transparent;
                    }}
                    QLabel#sectionHeaderText {{
                        color: {"#F25582" if not dark else BRAND};
                        font-size: 13px;
                        font-weight: 600;
                        background: transparent;
                    }}
                    """
                )
        except Exception:
            pass
        try:
            divider = getattr(self, "tool_group_divider", None)
            if divider is not None:
                divider.setStyleSheet(
                    f"QFrame#toolGroupDivider {{ background: {'rgba(255,255,255,0.10)' if dark else '#EDF0F4'}; border: none; }}"
                )
        except Exception:
            pass
        try:
            for t in (getattr(self, 'debug_section_headers', None) or []):
                t.setStyleSheet(
                    f"QWidget#debugSectionHeader {{ background: {badge_bg}; border-radius: 8px; }}"
                    f"QLabel#sectionHeaderText {{ color: {BRAND}; background: transparent; font-size: 13px; font-weight: 700; }}"
                )
        except Exception:
            pass

        option_style = self.get_option_style()
        for cb in (self.auto_wrap, self.auto_time, self.auto_window, self.auto_music, self.auto_idle, self.auto_hr, self.auto_hardware, self.auto_cpu, self.auto_ram, self.auto_gpu, self.auto_temp, self.console_toggle):
            cb.setStyleSheet(option_style)

        # 调试值：状态类使用胶囊，CPU/RAM/GPU 百分比保持裸文字。
        try:
            for key, label in self.debug_labels.items():
                if label is None:
                    continue
                if label.objectName() == "statusPill":
                    label.setStyleSheet(
                        f"background: {pill_bg}; color: {secondary}; border-radius: 8px; "
                        f"padding: 1px 8px; font-size: 13px;"
                    )
                elif label.objectName() == "metricValue":
                    label.setStyleSheet(
                        f"background: transparent; color: {secondary}; border: none; "
                        f"font-size: 13px; font-weight: 600;"
                    )
                else:
                    label.setStyleSheet(f"color: {secondary}; font-size: 13px;")
            for bar in (getattr(self, "debug_bars", None) or {}).values():
                bar.setStyleSheet(
                    f"QProgressBar {{ background: {track_bg}; border: none; border-radius: 5px; }}"
                    f"QProgressBar::chunk {{ background-color: {BRAND}; border-radius: 5px; }}"
                )
        except Exception:
            pass
        try:
            for label in (getattr(self, "debug_left_labels", None) or {}).values():
                if label is not None:
                    label.setStyleSheet(f"color: {text}; font-size: 13px;")
            hr_key = getattr(self, "hr_key_label", None)
            if hr_key is not None:
                hr_key.setStyleSheet(f"color: {text}; font-size: 13px;")
        except Exception:
            pass

        self.char_count.setStyleSheet(f"color: {secondary}; font-size: 13px;")
        self.countdown_label.setStyleSheet(f"font-size: 10px; color: {secondary};")
        self.status_label.setStyleSheet(f"font-size: 13px; font-weight: 700; color: {text};")
        self.osc_addr.setStyleSheet("color: #000000; background: transparent; border: none;")
        try:
            empty_title = getattr(self, "history_empty_title", None)
            empty_hint = getattr(self, "history_empty_hint", None)
            if empty_title is not None:
                empty_title.setStyleSheet(f"color: {secondary}; font-size: 15px; font-weight: 600;")
            if empty_hint is not None:
                empty_hint.setStyleSheet(f"color: {TEXT_MUTED if not dark else secondary}; font-size: 12px;")
        except Exception:
            pass

        self.input_edit.setStyleSheet(f"""
            QTextEdit {{
                background: {panel_bg};
                border: 1px solid {panel_border};
                border-radius: 10px;
                padding: 12px;
                color: {text};
                font-size: 15px;
                selection-background-color: {accent};
                selection-color: #FFFFFF;
            }}
            QTextEdit:focus {{ border: 1px solid {accent}; }}
            QScrollBar:vertical {{
                background: transparent; width: 6px; margin: 0px; border-radius: 3px;
            }}
            QScrollBar::handle:vertical {{
                background: {accent_handle}; min-height: 24px; border-radius: 3px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        """)
        self.history_edit.setStyleSheet(f"""
            QTextEdit {{
                background: transparent;
                color: {text};
                font-size: 14px;
                font-weight: 500;
                border: none;

                padding-top: 12px;
                padding-left: 14px;
                padding-right: 14px;
                padding-bottom: 12px;

                selection-background-color: {accent};
                selection-color: #FFFFFF;
            }}

            QScrollBar:vertical {{
                background: transparent;
                width: 6px;
                margin: 0px;
                border-radius: 3px;
            }}

            QScrollBar::handle:vertical {{
                background: {accent_handle};
                min-height: 24px;
                border-radius: 3px;
            }}

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)

        # 面板对比度
        try:
            self._apply_panel_contrast()
        except Exception:
            pass

        try:
            self._attach_button_micro_interactions()
        except Exception:
            pass

    # 为按钮附加缩放与涟漪动效
    def _attach_button_micro_interactions(self):
        if getattr(self, '_micro_attached', False):
            return
        if not hasattr(self, '_btn_geo'):
            self._btn_geo = {}
        if not hasattr(self, '_btn_ripple'):
            self._btn_ripple = {}
        # Track primary action
        for btn in [self.start_btn, getattr(self, 'btn_open_settings', None)]:
            try:
                if btn is None:
                    continue
                self._btn_geo[btn] = btn.geometry()
                btn.pressed.connect(lambda b=btn: self._btn_press(b))
                btn.released.connect(lambda b=btn: self._btn_release(b))
                # Attach ripple overlay and trigger on press
                ripple = QRippleWidget(btn)
                self._btn_ripple[btn] = ripple
                btn.pressed.connect(lambda r=ripple: r.start(QCursor.pos()))
            except Exception:
                continue
        self._micro_attached = True

    # 按钮按下动画
    def _btn_press(self, btn: QPushButton):
        try:
            # 基准必须现取。_micro_button_setup 里记录的那份是在首次布局之前
            # 采样的脏值（实测 QRect(0,0,640,480)，而按钮实际在 (18,318,252,54)），
            # 一直沿用会让按钮在按下瞬间跳到左上角。
            self._btn_geo[btn] = btn.geometry()
            self._animate_button_scale(btn, 0.97)
        except Exception:
            pass

    # 按钮释放动画
    def _btn_release(self, btn: QPushButton):
        try:
            self._animate_button_scale(btn, 1.0)
        except Exception:
            pass

    # 按钮缩放动画实现
    def _animate_button_scale(self, btn: QPushButton, scale: float):
        if btn not in getattr(self, '_btn_geo', {}):
            self._btn_geo[btn] = btn.geometry()
        base = self._btn_geo[btn]
        w = base.width()
        h = base.height()
        new_w = int(w * scale)
        new_h = int(h * scale)
        dx = (w - new_w) // 2
        dy = (h - new_h) // 2
        target = QRect(base.x() + dx, base.y() + dy, new_w, new_h)
        # parent 必须给（第三个参数）：QPropertyAnimation 的第二个参数是「属性名」，
        # 若 parent 为 None，局部变量 anim 一返回就被 GC，动画一帧都不会跑
        # （PySide6 经典坑）。挂到 btn 上让它活到动画结束。
        anim = QPropertyAnimation(btn, b"geometry", btn)
        anim.setDuration(80)
        anim.setEasingCurve(QEasingCurve.InOutQuad)
        anim.setStartValue(btn.geometry())
        anim.setEndValue(target)
        anim.start()

    # 工具页与设置页复用的选项样式
    def get_option_style(self) -> str:
        dark = bool(getattr(self, "_theme_dark", True))
        text = "#F2F4F8" if dark else TEXT
        accent = BRAND
        border = "rgba(255,255,255,0.35)" if dark else "#C5CBD6"
        disabled_fill = DARK_PILL if dark else PILL_BG
        check_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "resources", "icons", "check.svg",
        ).replace("\\", "/")
        disabled_text = "#7E8796" if dark else "#8E98A9"
        # 注意：不要写成 f"...{ "x" if dark else "y" }..." —— 嵌套同种引号属于
        # PEP 701 语法，只有 CPython ≥ 3.12 能解析，在 3.10/3.11 上是 SyntaxError。
        disabled_border = "rgba(255,255,255,0.18)" if dark else "#D2D8E2"
        disabled_bg = "rgba(255,255,255,0.04)" if dark else "#F7F8FA"
        return (
            f"QCheckBox {{ color: {text}; font-size: 14px; spacing: 9px; }}"
            f"QCheckBox::indicator {{ width: 18px; height: 18px; "
            f"border: 1.4px solid {border}; border-radius: 5px; background: transparent; }}"
            f"QCheckBox::indicator:hover {{ border-color: {accent}; background: {rgba(BRAND, 0.04)}; }}"
            f"QCheckBox::indicator:checked {{ background-color: {accent}; "
            f"border-color: {accent}; image: url({check_path}); }}"
            f"QCheckBox:disabled {{ color: {disabled_text}; }}"
            f"QCheckBox::indicator:disabled {{ "
            f"border-color: {disabled_border}; "
            f"background: {disabled_bg}; }}"
        )

    # 切换性能模式（模糊/阴影/刷新频率）
    def set_performance_mode(self, enabled: bool):
        self.performance_mode = bool(enabled)
        try:
            # 性能模式只负责「强制关闭」阴影。重新打开时必须尊重用户独立的
            # 「圆角投影」偏好：原来无条件 on_shadow_toggle(not enabled)，于是
            # 用户关掉的投影会在关闭性能模式时（以及每次启动调用本方法时）被
            # 强行打开，而设置里仍显示为关闭。
            desired_shadow = bool(getattr(self, "_shadow_enabled", True)) and not enabled
            self.on_shadow_toggle(desired_shadow, record=False)
        except Exception:
            pass
        try:
            if enabled:
                self.input_panel.set_params(blur_strength=0, white_alpha=0)
                self.history_panel.set_params(blur_strength=0, white_alpha=0)
                self.tool_panel.set_params(blur_strength=0, white_alpha=0)
                self.debug_panel.set_params(blur_strength=0, white_alpha=0)
            else:
                # 退出性能模式应恢复「用户设定的」模糊强度。原来写死 6，
                # 于是设置里显示 14、实际却是 6，用户的选择被静默丢弃。
                restore = int(getattr(self, "_current_blur_strength", 6) or 0)
                self.input_panel.set_params(blur_strength=restore, white_alpha=0)
                self.history_panel.set_params(blur_strength=restore, white_alpha=0)
                self.tool_panel.set_params(blur_strength=restore, white_alpha=0)
                self.debug_panel.set_params(blur_strength=restore, white_alpha=0)
        except Exception:
            pass
        # 性能模式清零后，按壁纸亮度补回可读性遮罩
        try:
            self._apply_panel_contrast()
        except Exception:
            pass
        try:
            self.debug_timer.setInterval(2000 if enabled else 1000)
        except Exception:
            pass
        self._save_settings()

    # 切换静态模糊缓存
    def set_static_blur_enabled(self, enabled: bool):
        self.static_blur = bool(enabled)
        try:
            self.input_panel.set_static_blur(enabled)
            self.history_panel.set_static_blur(enabled)
            self.tool_panel.set_static_blur(enabled)
            self.debug_panel.set_static_blur(enabled)
        except Exception:
            pass
        self._save_settings()

    # 模糊强度滑条回调
    def on_strength_change(self, value: int):
        self._current_blur_strength = int(value)
        self.input_panel.set_params(blur_strength=value)
        self.history_panel.set_params(blur_strength=value)
        self.tool_panel.set_params(blur_strength=value)
        self.debug_panel.set_params(blur_strength=value)
        self._save_settings()

    # 白色遮罩透明度滑条回调
    def on_alpha_change(self, value: int):
        self._current_white_alpha = int(value)
        self.input_panel.set_params(white_alpha=value)
        self.history_panel.set_params(white_alpha=value)
        self.tool_panel.set_params(white_alpha=value)
        self.debug_panel.set_params(white_alpha=value)
        self._save_settings()

    # 圆角半径滑条回调
    def on_radius_change(self, value: int):
        self._current_corner_radius = int(value)
        self.input_panel.set_params(corner_radius=value)
        self.history_panel.set_params(corner_radius=value)
        self.tool_panel.set_params(corner_radius=value)
        self.debug_panel.set_params(corner_radius=value)
        self._save_settings()

    # 圆角投影开关回调
    def on_shadow_toggle(self, enabled: bool, record: bool = True):
        if record:
            self._shadow_enabled = bool(enabled)
        self.input_panel.set_shadow_enabled(enabled)
        self.history_panel.set_shadow_enabled(enabled)
        self.tool_panel.set_shadow_enabled(enabled)
        # 调试面板同样参与对比度处理，投影开关必须一并覆盖，否则它会一直保留阴影
        try:
            self.debug_panel.set_shadow_enabled(enabled)
        except Exception:
            pass
        if record:
            self._save_settings()

    # 亚克力效果开关回调
    def toggle_acrylic(self, checked: bool):
        self._acrylic_enabled = bool(checked)
        try:
            if checked:
                self.input_panel.set_params(blur_strength=self._current_blur_strength, white_alpha=self._current_white_alpha, corner_radius=self._current_corner_radius)
                self.history_panel.set_params(blur_strength=self._current_blur_strength, white_alpha=self._current_white_alpha, corner_radius=self._current_corner_radius)
                self.tool_panel.set_params(blur_strength=self._current_blur_strength, white_alpha=self._current_white_alpha, corner_radius=self._current_corner_radius)
                self.debug_panel.set_params(blur_strength=self._current_blur_strength, white_alpha=self._current_white_alpha, corner_radius=self._current_corner_radius)
            else:
                self.input_panel.set_params(blur_strength=0, white_alpha=0)
                self.history_panel.set_params(blur_strength=0, white_alpha=0)
                self.tool_panel.set_params(blur_strength=0, white_alpha=0)
                self.debug_panel.set_params(blur_strength=0, white_alpha=0)
        except Exception:
            pass
        self._save_settings()
