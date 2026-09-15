"""Settings dialog."""

import os
from PySide6.QtCore import Qt, QSize, QRect, QPropertyAnimation, QSequentialAnimationGroup, QEasingCurve, QVariantAnimation
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QStyle,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QCheckBox,
    QSlider,
    QSpinBox,
    QSizePolicy,
    QWidget,
    QSplitter,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
    QFrame,
    QScrollArea,
)
from PySide6.QtGui import QColor, QCursor, QIcon

from app.ui.design import (
    BRAND, BRAND_SOFT, BRAND_SOFT_2, TEXT, TEXT_SECONDARY, TEXT_MUTED,
    CARD, BORDER, PILL_BG,
)
from app.ui.widgets import QRippleWidget, ToggleSwitch, HoverCard


def _material_ease(t: float) -> float:
    """cubic-bezier(0.4, 0, 0.2, 1) 标准缓动（牛顿法反解贝塞尔参数）。"""
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0

    def bez(p0, p1, p2, p3, u):
        inv = 1.0 - u
        return inv * inv * inv * p0 + 3 * inv * inv * u * p1 + 3 * inv * u * u * p2 + u * u * u * p3

    u = t
    for _ in range(10):
        x = bez(0.0, 0.4, 0.2, 1.0, u) - t
        dx = 3 * 0.4 * (1 - u) * (1 - 3 * u) + 3 * 0.2 * u * (2 - 3 * u) + 3 * u * u
        if abs(dx) < 1e-8:
            break
        u = max(0.0, min(1.0, u - x / dx))
    return bez(0.0, 0.0, 1.0, 1.0, u)


class SettingsDialog(QDialog):
    def __init__(self, main):
        super().__init__(main)
        self.main = main
        # 品牌粉配色：与主界面一致，不跟系统强调色
        _dark = bool(getattr(self.main, "_theme_dark", True))
        self._pal = {
            "dark": _dark,
            "text": "#F2F4F8" if _dark else TEXT,
            "secondary": "#A8B0C0" if _dark else TEXT_SECONDARY,
            "faint": "#7E8796" if _dark else TEXT_MUTED,
            "accent": BRAND,
            "sidebar_bg": "#20232A" if _dark else "#FAFBFC",
            "content_bg": "#181B20" if _dark else "#F7F8FA",
            "card_bg": "#252932" if _dark else CARD,
            "card_border": "rgba(255,255,255,0.10)" if _dark else BORDER,
            "divider": "rgba(255,255,255,0.08)" if _dark else "#EDF0F4",
            "nav_selected": "rgba(244,91,138,0.18)" if _dark else BRAND_SOFT,
            "nav_hover": "rgba(244,91,138,0.10)" if _dark else "#FFF6F8",
            "hint": "#F3B35C" if _dark else "#C98218",
            "indicator": BRAND,
        }
        self.setWindowTitle("设置")
        # 去掉左上角标题栏图标
        self.setWindowIcon(QIcon())
        self.resize(920, 560)
        self.setMinimumSize(820, 500)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # 左右分栏：左侧分类 + 右侧页面
        splitter = QSplitter(Qt.Horizontal)
        left_panel = QListWidget()
        # 右侧改为滚动区域容器，支持每个页面独立滚动
        right_panel = QScrollArea()
        right_panel.setWidgetResizable(True)
        right_panel.setFrameShape(QFrame.NoFrame)
        right_panel.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(0)
        right_panel.setWidget(scroll_widget)
        # 保存引用用于切换
        self.scroll_layout = scroll_layout
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([195, 725])

        # 设置左侧导航的宽度范围，避免过窄或过宽
        left_panel.setMinimumWidth(185)
        left_panel.setMaximumWidth(205)

        # 左侧导航样式（Windows 设置风格：深灰/浅灰侧栏 + 圆角选中项）
        p = self._pal
        self.left_panel = left_panel
        left_panel.setStyleSheet(f"""
            QListWidget {{
                border: none;
                background-color: {p['sidebar_bg']};
                outline: none;
                font-family: "Segoe UI Variable", "Microsoft YaHei UI",
                             "Microsoft YaHei", sans-serif;
                font-size: 14px;
                color: {p['text']};
                padding-top: 14px;
            }}

            QListWidget::item {{
                height: 42px;
                padding: 0 14px;
                border-radius: 9px;
                margin: 3px 10px;
                border: none;
            }}

            QListWidget::item:selected {{
                background-color: {p['nav_selected']};
                color: {BRAND};
                font-weight: 600;
            }}

            QListWidget::item:hover:!selected {{
                background-color: {p['nav_hover']};
            }}
        """)

        # 左侧选中指示条：切换选项时旧位置收缩、新位置延伸
        self._indicator = QWidget(left_panel.viewport())
        self._indicator.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._indicator.setFixedWidth(4)
        self._indicator.setStyleSheet(
            f"background-color: {BRAND}; border-radius: 2px;"
        )
        self._indicator.hide()
        self._nav_anim = None
        self._last_nav_row = 0

        # 选中背景“液体滑动”高亮块：暂不叠加（item:selected 已有粉底）
        self._nav_highlight = QWidget(left_panel.viewport())
        self._nav_highlight.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._nav_highlight.setStyleSheet(
            f"background-color: {p['nav_selected']}; border-radius: 6px;"
        )
        self._nav_highlight.hide()
        self._nav_highlight_anim = None
        self._last_highlight_row = 0

        # 右侧内容区：跟随主题的背景，去掉原来的纯白写死
        right_panel.setObjectName("settingsContent")
        right_panel.viewport().setObjectName("settingsViewport")
        scroll_widget.setObjectName("settingsScrollWidget")
        right_panel.setStyleSheet(f"""
            #settingsContent, #settingsViewport, #settingsScrollWidget {{
                background-color: {p['content_bg']};
            }}
        """)

        # 对话框整体与控件的基础样式（Windows 设置风格）
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {p['content_bg']};
                color: {p['text']};
                font-family: "Segoe UI Variable", "Segoe UI", sans-serif;
            }}
            QLabel {{
                color: {p['text']};
            }}
            QSpinBox {{
                background-color: {p['card_bg']};
                color: {p['text']};
                border: 1px solid {p['card_border']};
                border-radius: 4px;
                padding: 2px 6px;
            }}
            QSlider::groove:horizontal {{
                height: 4px;
                background: {p['divider']};
                border-radius: 2px;
            }}
            QSlider::sub-page:horizontal {{
                background: {p['accent']};
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                width: 14px;
                height: 14px;
                margin: -5px 0;
                border-radius: 7px;
                background: {p['text']};
            }}
        """)
        # 去掉左右分栏之间的分割条
        splitter.setHandleWidth(0)
        splitter.setChildrenCollapsible(False)

        # 创建页面（暂不使用系统标准图标，避免干扰文字显示）
        self.pages = [
            ("外观", None, self._create_appearance_page()),
            ("性能", None, self._create_performance_page()),
            ("间隔", None, self._create_interval_page()),
            ("背景", None, self._create_background_page()),
            ("插件", None, self._create_plugins_page()),
        ]

        for name, _icon, _page in self.pages:
            item = QListWidgetItem()
            item.setText(name)
            item.setSizeHint(QSize(0, 44))
            item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            left_panel.addItem(item)

        # 防止第一页名称被错误覆盖
        if left_panel.count() > 0:
            left_panel.item(0).setText("外观")

        # 信号连接：左侧切换当前页
        left_panel.currentRowChanged.connect(self.switch_page)
        left_panel.currentRowChanged.connect(self._animate_nav_indicator)
        # 暂不叠加灰色滑动高亮，避免与 item:selected 粉底叠色
        # left_panel.currentRowChanged.connect(self._slide_nav_highlight)
        # 初始化显示第一页
        left_panel.setCurrentRow(0)
        self.switch_page(0)

        main_layout.addWidget(splitter)

        # 底部操作栏：全局重置 + 关闭
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        close_btn = buttons.button(QDialogButtonBox.Close)
        if close_btn is not None:
            close_btn.setText("关闭")
        for b in buttons.buttons():
            b.setFlat(True)
            b.setStyleSheet(self._flat_button_style())

        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(16, 8, 16, 10)
        bottom_bar.setSpacing(8)
        self.btn_global_reset = QPushButton("恢复默认")
        try:
            self.btn_global_reset.setIcon(self.main.get_icon('refresh'))
            self.btn_global_reset.setIconSize(QSize(18, 18))
        except Exception:
            pass
        self.btn_global_reset.setFlat(True)
        self.btn_global_reset.setStyleSheet(self._flat_button_style())
        self.btn_global_reset.clicked.connect(self.on_reset_defaults)
        bottom_bar.addWidget(self.btn_global_reset)
        bottom_bar.addStretch(1)
        bottom_bar.addWidget(buttons)
        try:
            rp = QRippleWidget(self.btn_global_reset)
            self.btn_global_reset.pressed.connect(lambda r=rp: r.start(QCursor.pos()))
        except Exception:
            pass
        main_layout.addLayout(bottom_bar)

    def _style_option_checkbox(self, cb) -> None:
        """设置页选项样式：开关控件自行绘制，普通复选框使用工具页样式。"""
        if isinstance(cb, ToggleSwitch):
            return
        try:
            style = self.main.get_option_style()
        except Exception:
            style = "color: #1A1A1A; font-size: 14px;"
        try:
            cb.setStyleSheet(style)
        except Exception:
            pass

    def _flat_button_style(self) -> str:
        """Windows 设置风格的扁平按钮样式。"""
        p = self._pal
        return (
            f"QPushButton {{ border-radius: 8px; padding: 6px 12px; "
            f"background: transparent; color: {p['text']}; }}"
            f"QPushButton:hover {{ background-color: {p['nav_hover']}; }}"
        )

    def _card_style(self) -> str:
        """设置项卡片样式：只作用于卡片本身，不传染给内部子控件。"""
        p = self._pal

        if p["dark"]:
            bg = "#252932"
            border = "rgba(255,255,255,0.10)"
        else:
            bg = "#FFFFFF"
            border = "#E6EAF0"

        return f"""
            QWidget#settingCard {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 12px;
            }}
        """

    def _wrap_card_layout(self, layout) -> QWidget:
        """稳定的布局设置卡片（QFrame，不依赖 HoverCard）。"""
        p = self._pal

        card = QFrame()
        card.setObjectName("settingCard")
        card.setFrameShape(QFrame.NoFrame)

        card.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed
        )
        card.setMinimumHeight(86)

        inner = QVBoxLayout(card)
        inner.setContentsMargins(18, 14, 18, 14)
        inner.setSpacing(6)
        inner.addLayout(layout)

        card.setStyleSheet(f"""
            QFrame#settingCard {{
                background-color: {"#252932" if p["dark"] else "#FFFFFF"};
                border: 1px solid {
                    "rgba(255,255,255,0.10)"
                    if p["dark"]
                    else "#E3E8EF"
                };
                border-radius: 12px;
            }}
        """)

        return card

    def _row_label(self, text: str) -> QLabel:
        """行内文字标签：固定宽度，避免被布局拉宽造成分栏错觉。"""
        lbl = QLabel(text)
        lbl.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        return lbl

    def _nav_item_rect(self, row: int) -> QRect:
        """获取左侧导航某个选项的矩形区域。"""
        item = self.left_panel.item(row)
        return self.left_panel.visualItemRect(item) if item is not None else QRect()

    def _indicator_rect(self, row: int) -> QRect:
        """指示条矩形：贴近左侧（略内缩）、高度约为选项的 55%。"""
        r = self._nav_item_rect(row)
        if r.isEmpty():
            return QRect()
        bar_h = max(12, int(r.height() * 0.55))
        y = r.y() + (r.height() - bar_h) // 2
        return QRect(4, y, 3, bar_h)

    def _animate_nav_indicator(self, row: int) -> None:
        """切换导航选项：旧位置竖线收缩，新位置竖线延伸（复用同一动画组）。"""
        old_row = getattr(self, "_last_nav_row", 0)
        self._last_nav_row = row
        old_rect = self._indicator_rect(old_row)
        new_rect = self._indicator_rect(row)
        if old_rect.isEmpty() or new_rect.isEmpty():
            return
        if row == old_row:
            # 首次显示或原地刷新：直接定位（并停止可能仍在运行的动画）
            self._stop_nav_animations()
            self._indicator.setGeometry(new_rect)
            self._indicator.show()
            self._indicator.raise_()
            return

        self._indicator.show()
        self._indicator.raise_()
        self._indicator.setGeometry(old_rect)

        group = self._ensure_nav_anim_group()
        moving_down = row > old_row
        anim1, anim2 = self._nav_anim1, self._nav_anim2

        # 第一段：旧线向新选项方向拉伸到底部/顶部，然后消失
        anim1.setDuration(200)
        anim1.setEasingCurve(QEasingCurve.OutCubic)
        anim1.setStartValue(old_rect)
        if moving_down:
            stretch_bottom = new_rect.y() + new_rect.height()
            anim1.setKeyValueAt(0.5, QRect(old_rect.x(), old_rect.y(), 3, stretch_bottom - old_rect.y()))
            anim1.setEndValue(QRect(old_rect.x(), stretch_bottom, 3, 0))
        else:
            stretch_top = new_rect.y()
            old_bottom = old_rect.y() + old_rect.height()
            anim1.setKeyValueAt(0.5, QRect(old_rect.x(), stretch_top, 3, old_bottom - stretch_top))
            anim1.setEndValue(QRect(old_rect.x(), stretch_top, 3, 0))

        # 第二段：新位置的线先向相反方向过冲延伸，再回弹到正常样式
        anim2.setDuration(240)
        anim2.setEasingCurve(QEasingCurve.OutCubic)
        if moving_down:
            overshoot = min(24.0, (new_rect.y() - old_rect.y()) * 0.5)
            anim2.setStartValue(QRect(new_rect.x(), new_rect.y(), 3, 0))
            anim2.setKeyValueAt(0.55, QRect(new_rect.x(), new_rect.y() - overshoot, 3, new_rect.height() + overshoot))
            anim2.setEndValue(new_rect)
        else:
            overshoot = min(24.0, (old_rect.y() - new_rect.y()) * 0.5)
            anim2.setStartValue(QRect(new_rect.x(), new_rect.y() + new_rect.height(), 3, 0))
            anim2.setKeyValueAt(0.55, QRect(new_rect.x(), new_rect.y(), 3, new_rect.height() + overshoot))
            anim2.setEndValue(new_rect)

        # 复用同一动画组：start() 前必须先 stop()，
        # 否则动画播放中再次点击时 start() 无效，动画不会重启
        group.stop()
        group.start()

    def _ensure_nav_anim_group(self):
        """惰性创建并复用指示条动画组（避免每次切换新建对象）。"""
        group = getattr(self, '_nav_anim', None)
        if group is None:
            group = QSequentialAnimationGroup(self._indicator)
            self._nav_anim1 = QPropertyAnimation(self._indicator, b"geometry")
            self._nav_anim2 = QPropertyAnimation(self._indicator, b"geometry")
            group.addAnimation(self._nav_anim1)
            group.addAnimation(self._nav_anim2)
            self._nav_anim = group
        return group

    def _stop_nav_animations(self):
        """停止导航指示条动画（复用实例，无需删除对象）。"""
        group = getattr(self, '_nav_anim', None)
        if group is not None:
            try:
                group.stop()
            except Exception:
                pass

    def _nav_highlight_rect(self, row: int) -> QRect:
        """高亮块矩形：与列表项的内边距对齐（左右 8px、上下 2px）。"""
        r = self._nav_item_rect(row)
        if r.isEmpty():
            return QRect()
        return QRect(r.x() + 8, r.y() + 2, r.width() - 16, r.height() - 4)

    def _slide_nav_highlight(self, row: int) -> None:
        """选中背景像液体一样滑到新位置（300ms，复用同一个动画实例）。"""
        old_row = getattr(self, "_last_highlight_row", 0)
        self._last_highlight_row = row
        old_rect = self._nav_highlight_rect(old_row)
        new_rect = self._nav_highlight_rect(row)
        if old_rect.isEmpty() or new_rect.isEmpty():
            return
        if row == old_row:
            # 首次显示/原地刷新：直接定位（并停止可能仍在运行的动画）
            anim = getattr(self, '_nav_highlight_anim', None)
            if anim is not None:
                try:
                    anim.stop()
                except Exception:
                    pass
            self._nav_highlight.setGeometry(new_rect)
            self._nav_highlight.show()
            self._nav_highlight.raise_()
            return
        self._nav_highlight.show()
        self._nav_highlight.raise_()
        self._nav_highlight.setGeometry(old_rect)

        # 用 QVariantAnimation 在 Python 侧按 cubic-bezier(0.4, 0, 0.2, 1) 插值，
        # 避免 QEasingCurve 自定义回调在动画运行时的兼容问题
        anim = self._nav_highlight_anim
        if anim is None:
            anim = QVariantAnimation(self)
            anim.setDuration(300)
            anim.valueChanged.connect(self._slide_highlight_frame)
            self._nav_highlight_anim = anim
        # 记录本次起止矩形，供帧回调插值
        self._slide_old_rect = old_rect
        self._slide_new_rect = new_rect
        anim.stop()
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.start()

    def _slide_highlight_frame(self, progress: float):
        t = _material_ease(float(progress))
        old_rect = getattr(self, '_slide_old_rect', QRect())
        new_rect = getattr(self, '_slide_new_rect', QRect())
        geo = QRect(
            round(old_rect.x() + (new_rect.x() - old_rect.x()) * t),
            round(old_rect.y() + (new_rect.y() - old_rect.y()) * t),
            round(old_rect.width() + (new_rect.width() - old_rect.width()) * t),
            round(old_rect.height() + (new_rect.height() - old_rect.height()) * t),
        )
        self._nav_highlight.setGeometry(geo)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        try:
            # 先停止运行中的导航动画，避免动画下一帧覆盖 resize 后的位置
            self._stop_nav_animations()
            anim = getattr(self, '_nav_highlight_anim', None)
            if anim is not None:
                try:
                    anim.stop()
                except Exception:
                    pass
            row = getattr(self, "_last_nav_row", 0)
            rect = self._indicator_rect(row)
            if not rect.isEmpty():
                self._indicator.setGeometry(rect)
                self._indicator.show()
            hrect = self._nav_highlight_rect(row)
            if not hrect.isEmpty():
                self._nav_highlight.setGeometry(hrect)
                # 不再显示滑动高亮，避免盖住选中项文字
                self._nav_highlight.hide()
        except Exception:
            pass

    def on_reset_defaults(self):
        # 重置滑块到默认值
        self.sld_strength.setValue(14)
        self.sld_alpha.setValue(28)
        self.sld_radius.setValue(16)
        # 发送间隔同样属于“默认值”，之前漏掉了
        try:
            self.sld_interval.setValue(30)
        except Exception:
            pass

        # 重置外观相关复选框
        try:
            self.chk_acrylic.setChecked(True)
        except Exception:
            pass
        try:
            self.chk_shadow.setChecked(True)
        except Exception:
            pass

        # 重置性能相关复选框
        try:
            self.chk_static_blur.setChecked(False)
        except Exception:
            pass
        try:
            self.chk_perf.setChecked(False)
        except Exception:
            pass

        # 重置背景为纯白
        try:
            self.chk_plain.setChecked(True)
        except Exception:
            pass

    def on_choose_wallpaper(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择壁纸", os.path.expanduser("~"), "图片 (*.png *.jpg *.jpeg *.bmp *.gif)")
        if path:
            self.chk_plain.setChecked(False)
            self.main.set_plain_background_enabled(False)
            self.main.set_custom_wallpaper(path)
            self.update_path_label()

    def on_reset_wallpaper(self):
        self.chk_plain.setChecked(False)
        self.main.set_plain_background_enabled(False)
        self.main.set_custom_wallpaper(None)
        self.update_path_label()

    def on_toggle_plain(self, enabled: bool):
        self.main.set_plain_background_enabled(enabled)
        self.update_path_label()

    def update_path_label(self):
        if self.main.use_plain_background:
            self.lbl_path.setText("当前: 纯白背景")
        elif self.main.custom_wallpaper_path:
            self.lbl_path.setText(self.main.custom_wallpaper_path)
        else:
            self.lbl_path.setText("当前: 系统壁纸")

    def update_high_blur_hint(self):
        try:
            strength = int(self.sld_strength.value())
        except Exception:
            strength = 0
        try:
            alpha = int(self.sld_alpha.value())
        except Exception:
            alpha = 0
        if strength >= 20:
            if alpha >= 20:
                self.lbl_high_blur_hint.setText("提示：高模糊下建议降低白色遮罩，以避免发灰效果")
            else:
                self.lbl_high_blur_hint.setText("提示：高模糊下可适当降低白色遮罩，提升通透感")

    def switch_page(self, index: int):
        """切换页面：清空滚动布局并添加目标页"""
        try:
            # 清空当前滚动内容
            while self.scroll_layout.count():
                item = self.scroll_layout.takeAt(0)
                if item and item.widget():
                    item.widget().setParent(None)
            # 添加新页面
            if 0 <= index < len(getattr(self, 'pages', [])):
                self.scroll_layout.addWidget(self.pages[index][2])
        except Exception:
            pass
        
    # --- 页面构建 ---
    def _create_appearance_page(self) -> QWidget:
        page = QWidget()
        p = self._pal
        layout = QVBoxLayout(page)
        layout.setContentsMargins(26, 22, 26, 22)
        layout.setSpacing(14)

        title = QLabel("外观")
        title.setStyleSheet(
            f"font-size: 22px; font-weight: 700; color: {p['text']};"
        )
        layout.addWidget(title)

        subtitle = QLabel(
            "个性化 VRCOSC Pulse 的外观，打造更舒适的使用体验。"
        )
        subtitle.setStyleSheet(
            f"font-size: 13px; color: {p['secondary']};"
        )
        layout.addWidget(subtitle)
        layout.addSpacing(10)

        self.chk_acrylic = ToggleSwitch("启用亚克力效果")
        self.chk_acrylic.setChecked(bool(getattr(self.main, '_acrylic_enabled', True)))
        self._style_option_checkbox(self.chk_acrylic)
        self.chk_acrylic.stateChanged.connect(lambda s: self.main.toggle_acrylic(bool(s)))

        acrylic_layout = QVBoxLayout()
        acrylic_layout.setContentsMargins(0, 0, 0, 0)
        acrylic_layout.setSpacing(4)
        acrylic_layout.addWidget(self.chk_acrylic)
        acrylic_hint = QLabel("为主窗口启用透明模糊与亚克力视觉效果")
        acrylic_hint.setStyleSheet(
            f"color: {p['secondary']}; font-size: 12px; background: transparent; border: none;"
        )
        acrylic_layout.addWidget(acrylic_hint)
        layout.addWidget(self._wrap_card_layout(acrylic_layout))
        layout.addSpacing(4)

        self.chk_shadow = ToggleSwitch("圆角投影")
        self.chk_shadow.setChecked(bool(getattr(self.main, '_shadow_enabled', True)))
        self._style_option_checkbox(self.chk_shadow)
        self.chk_shadow.stateChanged.connect(lambda s: self.main.on_shadow_toggle(bool(s)))

        shadow_layout = QVBoxLayout()
        shadow_layout.setContentsMargins(0, 0, 0, 0)
        shadow_layout.setSpacing(4)
        shadow_layout.addWidget(self.chk_shadow)
        shadow_hint = QLabel("为窗口与卡片增加柔和圆角阴影")
        shadow_hint.setStyleSheet(
            f"color: {p['secondary']}; font-size: 12px; background: transparent; border: none;"
        )
        shadow_layout.addWidget(shadow_hint)
        layout.addWidget(self._wrap_card_layout(shadow_layout))
        layout.addSpacing(4)

        preview_box = QWidget()
        preview_box.setObjectName("settingsHint")
        preview_layout = QHBoxLayout(preview_box)
        preview_layout.setContentsMargins(14, 0, 14, 0)
        preview_label = QLabel("ⓘ  更改将实时生效")
        preview_label.setStyleSheet(
            f"color: {BRAND}; font-size: 13px; font-weight: 500;"
        )
        preview_layout.addWidget(preview_label)
        preview_box.setFixedHeight(48)
        preview_box.setStyleSheet(f"""
            QWidget#settingsHint {{
                background-color: #FFF0F4;
                border: none;
                border-radius: 10px;
            }}
        """)
        layout.addWidget(preview_box)

        layout.addStretch(1)
        return page

    def _value_pill(self, text: str) -> QLabel:
        """滑块右侧数值小胶囊。"""
        p = self._pal
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setFixedSize(44, 28)
        lbl.setStyleSheet(f"""
            QLabel {{
                background-color: {"#30343D" if p["dark"] else "#F2F4F7"};
                color: {p["secondary"]};
                border: none;
                border-radius: 8px;
                font-size: 12px;
                font-weight: 500;
            }}
        """)
        return lbl

    def _create_performance_page(self) -> QWidget:
        page = QWidget()
        p = self._pal
        layout = QVBoxLayout(page)
        layout.setContentsMargins(26, 20, 26, 18)
        layout.setSpacing(10)

        title = QLabel("性能")
        title.setStyleSheet(f"font-size: 22px; font-weight: 700; color: {p['text']};")
        layout.addWidget(title)
        subtitle = QLabel("调整模糊、透明度和渲染性能")
        subtitle.setStyleSheet(f"color: {p['secondary']}; font-size: 13px;")
        layout.addWidget(subtitle)
        layout.addSpacing(8)

        # 分区标题 + 本页重置
        section_row = QHBoxLayout()
        section_row.setContentsMargins(0, 0, 0, 0)
        section_row.setSpacing(8)
        section_title = QLabel("模糊效果")
        section_title.setStyleSheet(
            f"color: {p['text']}; font-size: 14px; font-weight: 600;"
        )
        section_row.addWidget(section_title)
        section_row.addStretch(1)
        reset_btn = QPushButton("恢复性能默认")
        reset_btn.setObjectName("ghostBtn")
        reset_btn.setCursor(Qt.PointingHandCursor)
        reset_btn.setFixedHeight(30)
        reset_btn.setStyleSheet(self._flat_button_style())
        reset_btn.clicked.connect(self.on_reset_defaults)
        section_row.addWidget(reset_btn)
        layout.addLayout(section_row)

        def _slider_row(label_text, slider, value_label):
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)
            row.addWidget(self._row_label(label_text))
            row.addStretch(1)
            row.addWidget(slider)
            row.addSpacing(12)
            row.addWidget(value_label)
            return row

        # 外观滑条必须回填「当前生效值」：此前一律硬编码 14/28/16，用户把模糊
        # 设成 20 后重开对话框仍显示 14，界面与实际外观长期不一致。
        # 注意 setValue 必须排在 connect 之前，否则构造对话框时就会触发
        # on_*_change 反向覆盖用户设置。
        def _current(attr: str, default: int) -> int:
            try:
                return int(getattr(self.main, attr, default))
            except Exception:
                return default

        cur_strength = _current("_current_blur_strength", 14)
        cur_alpha = _current("_current_white_alpha", 28)
        cur_radius = _current("_current_corner_radius", 16)

        # 模糊强度
        self.sld_strength = QSlider(Qt.Horizontal)
        self.sld_strength.setRange(0, 40)
        self.sld_strength.setValue(cur_strength)
        self.sld_strength.setFixedWidth(210)
        self.sld_strength.valueChanged.connect(self.main.on_strength_change)
        self.lbl_strength = self._value_pill(str(cur_strength))
        self.sld_strength.valueChanged.connect(lambda v: self.lbl_strength.setText(str(v)))
        self.sld_strength.valueChanged.connect(lambda v: self.update_high_blur_hint())
        blur_card = self._wrap_card_layout(_slider_row("模糊强度", self.sld_strength, self.lbl_strength))
        blur_card.setFixedHeight(74)
        layout.addWidget(blur_card)

        # 白色遮罩透明度
        self.sld_alpha = QSlider(Qt.Horizontal)
        self.sld_alpha.setRange(0, 100)
        self.sld_alpha.setValue(cur_alpha)
        self.sld_alpha.setFixedWidth(210)
        self.sld_alpha.valueChanged.connect(self.main.on_alpha_change)
        self.lbl_alpha = self._value_pill(str(cur_alpha))
        self.sld_alpha.valueChanged.connect(lambda v: self.lbl_alpha.setText(str(v)))
        self.sld_alpha.valueChanged.connect(lambda v: self.update_high_blur_hint())
        mask_card = self._wrap_card_layout(_slider_row("白色遮罩透明度", self.sld_alpha, self.lbl_alpha))
        mask_card.setFixedHeight(74)
        layout.addWidget(mask_card)

        # 圆角半径
        self.sld_radius = QSlider(Qt.Horizontal)
        self.sld_radius.setRange(0, 32)
        self.sld_radius.setValue(cur_radius)
        self.sld_radius.setFixedWidth(210)
        self.sld_radius.valueChanged.connect(self.main.on_radius_change)
        self.lbl_radius = self._value_pill(str(cur_radius))
        self.sld_radius.valueChanged.connect(lambda v: self.lbl_radius.setText(str(v)))
        radius_card = self._wrap_card_layout(_slider_row("圆角半径", self.sld_radius, self.lbl_radius))
        radius_card.setFixedHeight(74)
        layout.addWidget(radius_card)

        # 高模糊提示（紧凑一行）
        self.lbl_high_blur_hint = QLabel("")
        self.lbl_high_blur_hint.setWordWrap(True)
        self.lbl_high_blur_hint.setStyleSheet(f"color: {p['hint']}; font-size: 12px;")
        layout.addWidget(self.lbl_high_blur_hint)

        layout.addSpacing(4)

        # 静态模糊背景
        self.chk_static_blur = ToggleSwitch("静态模糊背景")
        self.chk_static_blur.setToolTip("缓存背景模糊效果，提升性能但切换背景时需要手动刷新")
        self.chk_static_blur.setChecked(self.main.static_blur)
        self._style_option_checkbox(self.chk_static_blur)
        self.chk_static_blur.stateChanged.connect(lambda s: self.main.set_static_blur_enabled(bool(s)))
        static_layout = QVBoxLayout()
        static_layout.setContentsMargins(0, 0, 0, 0)
        static_layout.setSpacing(4)
        static_layout.addWidget(self.chk_static_blur)
        static_hint = QLabel("缓存模糊背景，减少重复计算并降低资源占用")
        static_hint.setStyleSheet(
            f"color: {p['secondary']}; font-size: 12px; background: transparent;"
        )
        static_layout.addWidget(static_hint)
        static_card = self._wrap_card_layout(static_layout)
        static_card.setFixedHeight(76)
        layout.addWidget(static_card)

        # 性能模式
        self.chk_perf = ToggleSwitch("性能模式")
        self.chk_perf.setChecked(self.main.performance_mode)
        self._style_option_checkbox(self.chk_perf)
        self.chk_perf.stateChanged.connect(lambda s: self.main.set_performance_mode(bool(s)))
        performance_layout = QVBoxLayout()
        performance_layout.setContentsMargins(0, 0, 0, 0)
        performance_layout.setSpacing(4)
        performance_layout.addWidget(self.chk_perf)
        performance_hint = QLabel("降低部分模糊与阴影效果，以换取更流畅的界面")
        performance_hint.setStyleSheet(
            f"color: {p['secondary']}; font-size: 12px; background: transparent;"
        )
        performance_layout.addWidget(performance_hint)
        performance_card = self._wrap_card_layout(performance_layout)
        performance_card.setFixedHeight(76)
        layout.addWidget(performance_card)

        layout.addStretch(1)
        try:
            self.update_high_blur_hint()
        except Exception:
            pass
        return page

    def _create_interval_page(self) -> QWidget:
        """间隔分区页：自动发送间隔（滑块，与性能页一致）+ OSC 地址。"""
        page = QWidget()
        p = self._pal
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)

        title = QLabel("间隔")
        title.setStyleSheet(f"font-size: 22px; font-weight: 700; color: {p['text']};")
        layout.addWidget(title)
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFixedHeight(1)
        line.setStyleSheet(f"background-color: {p['divider']}; border: none; margin: 8px 0 16px 0;")
        layout.addWidget(line)

        # 自动发送间隔：滑块 + 数字显示（与性能页滑块样式一致）
        try:
            cur = int(getattr(self.main, 'spin_interval', None).value())
        except Exception:
            cur = 30
        self.sld_interval = QSlider(Qt.Horizontal)
        self.sld_interval.setRange(5, 3600)
        self.sld_interval.setValue(cur)
        self.sld_interval.setSingleStep(5)
        self.sld_interval.setFixedWidth(220)
        self.sld_interval.valueChanged.connect(self.main.spin_interval.setValue)
        self.lbl_interval = QLabel(str(cur))
        self.lbl_interval.setStyleSheet(f"color: {p['secondary']}; font-weight: 500;")
        self.lbl_interval.setFixedWidth(48)
        self.lbl_interval.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.sld_interval.valueChanged.connect(lambda v: self.lbl_interval.setText(str(v)))
        interval_row = QHBoxLayout()
        interval_row.addWidget(self._row_label("自动发送间隔（秒）"))
        interval_row.addStretch(1)
        interval_row.addWidget(self.sld_interval)
        interval_row.addWidget(self.lbl_interval)
        layout.addWidget(self._wrap_card_layout(interval_row))

        # OSC 目标地址：只读显示
        osc_row = QHBoxLayout()
        osc_row.addWidget(self._row_label("OSC 目标地址"))
        osc_row.addStretch(1)
        osc_lbl = QLabel("127.0.0.1:9000")
        osc_lbl.setStyleSheet(f"color: {p['secondary']};")
        osc_row.addWidget(osc_lbl)
        layout.addWidget(self._wrap_card_layout(osc_row))

        layout.addStretch(1)
        return page

    def _create_background_page(self) -> QWidget:
        page = QWidget()
        p = self._pal
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 20)  # 左右边距增加，上下保持20px
        layout.setSpacing(10)  # 进一步减少垂直间距

        title = QLabel("背景")
        title.setStyleSheet(f"font-size: 22px; font-weight: 700; color: {p['text']};")
        layout.addWidget(title)
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFixedHeight(1)
        line.setStyleSheet(f"background-color: {p['divider']}; border: none;")
        layout.addWidget(line)

        layout.addWidget(QLabel("背景源"))
        btn_row = QHBoxLayout()
        self.btn_choose = QPushButton("选择壁纸...")
        try:
            self.btn_choose.setIcon(self.main.get_icon('image'))
            self.btn_choose.setIconSize(QSize(18, 18))
        except Exception:
            pass
        self.btn_reset = QPushButton("使用系统壁纸")
        try:
            self.btn_reset.setIcon(self.main.get_icon('monitor'))
            self.btn_reset.setIconSize(QSize(18, 18))
        except Exception:
            pass
        self.chk_plain = ToggleSwitch("使用纯白背景（默认）")
        self.chk_plain.setChecked(self.main.use_plain_background)
        self._style_option_checkbox(self.chk_plain)
        self.lbl_path = QLabel("")
        self.lbl_path.setStyleSheet(f"color: {p['faint']};")
        btn_row.addWidget(self.btn_choose)
        btn_row.addWidget(self.btn_reset)
        btn_row.addStretch(1)
        for b in (self.btn_choose, self.btn_reset):
            b.setFlat(True)
            b.setStyleSheet(self._flat_button_style())
            try:
                rp = QRippleWidget(b)
                b.pressed.connect(lambda r=rp: r.start(QCursor.pos()))
            except Exception:
                pass
        # 背景设置卡片：按钮 + 纯白开关 + 当前路径
        bg_card = HoverCard()
        bg_card.set_card_style(self._card_style())
        bg_card.add_layout(btn_row)
        bg_card.add_widget(self.chk_plain)
        bg_card.add_widget(self.lbl_path)
        layout.addWidget(bg_card)

        self.btn_choose.clicked.connect(self.on_choose_wallpaper)
        self.btn_reset.clicked.connect(lambda: self.on_reset_wallpaper())
        self.chk_plain.stateChanged.connect(lambda s: self.on_toggle_plain(bool(s)))
        self.update_path_label()

        layout.addStretch(1)
        return page

    def _create_plugins_page(self) -> QWidget:
        page = QWidget()
        pal = self._pal
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("插件")
        title.setStyleSheet(f"font-size: 24px; font-weight: 600; color: {pal['text']};")
        layout.addWidget(title)
        try:
            pm = getattr(self.main, "plugin_manager", None)
            if pm is None or not hasattr(pm, "plugins") or not pm.plugins:
                no_plugins = QLabel("暂无可用插件")
                no_plugins.setStyleSheet(f"color: {pal['secondary']}; font-size: 14px;")
                no_plugins.setAlignment(Qt.AlignCenter)
                layout.addWidget(no_plugins)
            else:
                for p in pm.plugins:
                    try:
                        name = getattr(p, "name", "<unknown>")
                        desc = getattr(p, "description", "")
                        item = HoverCard()
                        item.set_card_style(
                            f"#settingCard {{ background-color: {pal['card_bg']}; "
                            f"border: 1px solid {pal['card_border']}; border-radius: 8px; }}"
                        )
                        item_layout = item.card_layout()
                        item_layout.setContentsMargins(8, 6, 8, 6)
                        item_layout.setSpacing(6)
                        title_lbl = QLabel(str(name))
                        title_lbl.setStyleSheet(f"font-weight: 600; color: {pal['text']};")
                        sub = QLabel(str(desc))
                        sub.setStyleSheet(f"color: {pal['secondary']};")
                        # 插件启用/禁用开关：胶囊放在插件名右侧
                        enable_cb = ToggleSwitch("")
                        enable_cb.setChecked(bool(getattr(p, "enabled", False)))
                        self._style_option_checkbox(enable_cb)
                        title_row = QHBoxLayout()
                        title_row.setContentsMargins(0, 0, 0, 0)
                        title_row.setSpacing(6)
                        title_row.addWidget(title_lbl, 1)
                        title_row.addWidget(enable_cb)
                        item_layout.addLayout(title_row)
                        if desc:
                            item_layout.addWidget(sub)
                        hint_label = QLabel("")
                        hint_label.setWordWrap(True)
                        hint_label.setStyleSheet(f"color: {pal['hint']}; font-size: 12px;")
                        hint_label.hide()

                        def _on_toggle(checked: bool, plugin=p, cb=enable_cb, hint=hint_label):
                            pmgr = getattr(self.main, "plugin_manager", None)
                            if pmgr is None:
                                return
                            ok, msg = pmgr.set_plugin_enabled(
                                getattr(plugin, "name", ""), bool(checked)
                            )
                            if ok:
                                hint.hide()
                                try:
                                    self.main._save_settings()
                                except Exception:
                                    pass
                            else:
                                cb.blockSignals(True)
                                cb.setChecked(False)
                                cb.blockSignals(False)
                                hint.setText(msg)
                                hint.show()

                        enable_cb.toggled.connect(_on_toggle)
                        item_layout.addWidget(hint_label)
                        cfgf = getattr(p, "create_settings_widget", None)
                        if callable(cfgf):
                            try:
                                w = cfgf(self)
                                if w is not None:
                                    item_layout.addWidget(w)
                            except Exception:
                                pass
                        layout.addWidget(item)
                    except Exception:
                        pass
        except Exception:
            pass
        layout.addStretch(1)
        return page
