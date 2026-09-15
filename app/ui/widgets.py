"""Custom widgets module.

Animated/utility controls used across the app.
"""

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Property, QPointF, QRect, QSize, Qt, QTimer
from PySide6.QtGui import QPainter, QColor, QRadialGradient, QBrush, QPalette, QCursor
from PySide6.QtWidgets import QApplication, QCheckBox, QWidget, QScrollBar, QGraphicsDropShadowEffect, QVBoxLayout


class HoverCard(QWidget):
    """可悬停的设置卡片。

    悬停时卡片整体上浮 2px，阴影由 0 1px 3px 扩散到 0 4px 12px，
    过渡 150ms ease-out；离开后平滑恢复。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("settingCard")
        self._inner = QVBoxLayout(self)
        self._inner.setContentsMargins(16, 12, 16, 12)
        self._inner.setSpacing(6)

        # 默认阴影：0 1px 3px
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(3)
        self._shadow.setOffset(0, 1)
        self._shadow.setColor(QColor(0, 0, 0, 45))
        self.setGraphicsEffect(self._shadow)

        self._lift = 0.0
        self._base_pos = None
        self._blur_anim = QPropertyAnimation(self._shadow, b"blurRadius")
        self._blur_anim.setDuration(150)
        self._blur_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._offset_anim = QPropertyAnimation(self._shadow, b"yOffset")
        self._offset_anim.setDuration(150)
        self._offset_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._color_anim = QPropertyAnimation(self._shadow, b"color")
        self._color_anim.setDuration(150)
        self._color_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._lift_anim = QPropertyAnimation(self, b"lift")
        self._lift_anim.setDuration(150)
        self._lift_anim.setEasingCurve(QEasingCurve.OutCubic)

    # --- 供设置页使用的接口 ---
    def set_card_style(self, qss: str) -> None:
        """应用卡片自身样式（只作用于内部卡片，不影响子控件）。"""
        self.setStyleSheet(qss)

    def card_layout(self) -> QVBoxLayout:
        """返回内部布局，用于填充内容。"""
        return self._inner

    def add_widget(self, widget) -> None:
        self._inner.addWidget(widget)

    def add_layout(self, layout) -> None:
        self._inner.addLayout(layout)

    # --- 上浮动效属性 ---
    def getLift(self) -> float:
        return float(self._lift)

    def setLift(self, value: float) -> None:
        self._lift = max(0.0, min(1.0, float(value)))
        if self._base_pos is not None:
            # 上浮 2px：以布局给的位置为基准向上移动
            self.move(self._base_pos.x(), self._base_pos.y() - round(2 * self._lift))

    lift = Property(float, getLift, setLift)

    # --- 悬停动画 ---
    def enterEvent(self, event):
        super().enterEvent(event)
        # 每次进入都重新取基准位置：布局变化（resize / 翻页 / 滚动）后旧的基准
        # 坐标会把卡片挪回过去的位置。仅在“未上浮”时重取，避免把偏移量当基准。
        if self._base_pos is None or self._lift <= 0.0:
            self._base_pos = self.pos()
        self._set_hover(True)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._set_hover(False)

    def _set_hover(self, hover: bool) -> None:
        for anim, end in (
            (self._blur_anim, 12 if hover else 3),
            (self._offset_anim, 4 if hover else 1),
            (self._lift_anim, 1.0 if hover else 0.0),
        ):
            anim.stop()
            anim.setStartValue(self._current_value(anim))
            anim.setEndValue(end)
            anim.start()
        # 阴影颜色透明度：45 -> 90
        color = self._shadow.color()
        target_alpha = 90 if hover else 45
        self._color_anim.stop()
        self._color_anim.setStartValue(QColor(color.red(), color.green(), color.blue(), color.alpha()))
        self._color_anim.setEndValue(QColor(color.red(), color.green(), color.blue(), target_alpha))
        self._color_anim.start()

    def _current_value(self, anim: QPropertyAnimation) -> object:
        name = bytes(anim.propertyName()).decode()
        if name == "blurRadius":
            return self._shadow.blurRadius()
        if name == "yOffset":
            return self._shadow.yOffset()
        if name == "lift":
            return self._lift
        return 0


class ToggleSwitch(QCheckBox):
    """Windows 11 风格开关：文字在左，胶囊开关在右。

    交互：
    - 鼠标悬停在开关上时小球轻微变大；
    - 单击左键：直接切换开关状态；
    - 按住超过阈值（长按）：小球变宽并可跟随鼠标在轨道内拖动（不会拖出轨道），
      松开后自动吸附到最近的一侧；
    - 点击文字/空白区域仍是整行切换。
    配色自动跟随宿主窗口的 _theme_dark 与 _accent。
    """

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)
        # 动画状态：0=关，1=开
        self._knob_pos = 1.0 if self.isChecked() else 0.0
        self._hover = 0.0      # 悬停放大比例
        self._press = 0.0      # 按住变宽比例
        self._tint = 1.0 if self.isChecked() else 0.0  # 轨道颜色混合
        self._pressed = False   # 左键是否按住开关
        self._dragging = False  # 是否已进入长按拖动状态

        # 长按判定：按住 260ms 后进入拖动模式
        self._drag_timer = QTimer(self)
        self._drag_timer.setSingleShot(True)
        self._drag_timer.setInterval(260)
        self._drag_timer.timeout.connect(self._enter_drag)

        # 小球位置动画（松手吸附/外部 setChecked）
        self._pos_anim = QPropertyAnimation(self, b"knobPos")
        self._pos_anim.setDuration(160)
        self._pos_anim.setEasingCurve(QEasingCurve.OutCubic)
        # 悬停放大动画
        self._hover_anim = QPropertyAnimation(self, b"hover")
        self._hover_anim.setDuration(120)
        self._hover_anim.setEasingCurve(QEasingCurve.OutCubic)
        # 按住变宽动画
        self._press_anim = QPropertyAnimation(self, b"press")
        self._press_anim.setDuration(90)
        self._press_anim.setEasingCurve(QEasingCurve.OutCubic)
        # 轨道颜色过渡动画
        self._tint_anim = QPropertyAnimation(self, b"tint")
        self._tint_anim.setDuration(180)
        self._tint_anim.setEasingCurve(QEasingCurve.OutCubic)
        self.toggled.connect(self._on_toggled)

    # --- Qt 动画属性 ---
    def getKnobPos(self) -> float:
        return float(self._knob_pos)

    def setKnobPos(self, value: float) -> None:
        self._knob_pos = max(0.0, min(1.0, float(value)))
        self.update()

    knobPos = Property(float, getKnobPos, setKnobPos)

    def getHover(self) -> float:
        return float(self._hover)

    def setHover(self, value: float) -> None:
        self._hover = max(0.0, min(1.0, float(value)))
        self.update()

    hover = Property(float, getHover, setHover)

    def getPress(self) -> float:
        return float(self._press)

    def setPress(self, value: float) -> None:
        self._press = max(0.0, min(1.0, float(value)))
        self.update()

    press = Property(float, getPress, setPress)

    def getTint(self) -> float:
        return float(self._tint)

    def setTint(self, value: float) -> None:
        self._tint = max(0.0, min(1.0, float(value)))
        self.update()

    tint = Property(float, getTint, setTint)

    def sizeHint(self):
        fm = self.fontMetrics()
        text_w = fm.horizontalAdvance(self.text())
        return QSize(text_w + 42 + 16, max(24, fm.height()))

    # --- 几何计算 ---
    def _switch_rect(self) -> QRect:
        rect = self.rect()
        sw_w, sw_h = 42, 22
        sw_x = rect.right() - sw_w - 2
        sw_y = rect.top() + max(0, (rect.height() - sw_h) // 2)
        return QRect(sw_x, sw_y, sw_w, sw_h)

    def _knob_size(self) -> tuple[float, float]:
        """返回 (宽, 高)：悬停放大，按住额外变宽。"""
        base = 14.0
        knob_h = base + self._hover * 4.0
        knob_w = knob_h + self._press * 6.0
        return knob_w, knob_h

    def _knob_range(self) -> tuple[float, float]:
        """小球中心可移动的左右边界（始终在轨道内）。"""
        sw = self._switch_rect()
        knob_w, knob_h = self._knob_size()
        pad = (sw.height() - knob_h) / 2.0
        left = sw.x() + pad + knob_w / 2.0
        right = sw.right() + 1 - pad - knob_w / 2.0
        return left, right

    def _set_pos_from_x(self, x: float) -> None:
        """拖动：根据鼠标 X 计算小球位置并限幅在轨道内。"""
        left, right = self._knob_range()
        pos = (x - left) / (right - left) if right > left else 0.0
        self._pos_anim.stop()
        self.setKnobPos(pos)

    def _enter_drag(self) -> None:
        """长按判定触发：进入拖动模式，小球跳到当前鼠标位置。"""
        if not self._pressed:
            return
        self._dragging = True
        self._set_pos_from_x(self.mapFromGlobal(QCursor.pos()).x())

    def _theme(self):
        """沿父链找到宿主主窗口，读取 (dark, accent_hex)。"""
        obj = self
        while obj is not None:
            dark = getattr(obj, "_theme_dark", None)
            if dark is not None:
                accent = getattr(obj, "_accent", None)
                return bool(dark), accent.name() if accent is not None else "#0078D4"
            obj = obj.parent() if hasattr(obj, "parent") else None
        return True, "#0078D4"

    # --- 动画辅助 ---
    def _animate_hover(self, target: float) -> None:
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover)
        self._hover_anim.setEndValue(target)
        self._hover_anim.start()

    def _animate_press(self, target: float) -> None:
        self._press_anim.stop()
        self._press_anim.setStartValue(self._press)
        self._press_anim.setEndValue(target)
        self._press_anim.start()

    def _animate_pos(self, target: float) -> None:
        self._pos_anim.stop()
        self._pos_anim.setStartValue(self._knob_pos)
        self._pos_anim.setEndValue(target)
        self._pos_anim.start()

    def _on_toggled(self, checked: bool) -> None:
        self._animate_pos(1.0 if checked else 0.0)
        self._tint_anim.stop()
        self._tint_anim.setStartValue(self._tint)
        self._tint_anim.setEndValue(1.0 if checked else 0.0)
        self._tint_anim.start()

    def setChecked(self, checked: bool) -> None:
        """同步设置选中状态。

        原生 QCheckBox 只通过 `toggled` 信号通知外观，而调用方经常用
        `blockSignals(True)` 包裹 `setChecked()`，那会把驱动小球/轨道动画的信号
        一并屏蔽，导致状态与外观脱节（例如「启用插件失败」回滚后小球仍停在右侧）。
        这里在信号被屏蔽时手动同步一次外观。
        """
        super().setChecked(bool(checked))
        if not self.signalsBlocked():
            # toggled 已发出并驱动了外观动画，无需重复
            return
        try:
            self._on_toggled(bool(self.isChecked()))
        except Exception:
            pass

    def _cursor_in_switch(self) -> bool:
        return self._switch_rect().contains(self.mapFromGlobal(QCursor.pos()))

    # --- 鼠标交互 ---
    def enterEvent(self, event):
        super().enterEvent(event)
        self._animate_hover(1.0 if self._cursor_in_switch() else 0.0)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._animate_hover(0.0)

    def mouseMoveEvent(self, event):
        if self._dragging:
            # 拖动：小球跟随鼠标（限幅在轨道内）
            self._set_pos_from_x(event.position().x())
            event.accept()
            return
        # 悬停：仅在开关范围内放大
        self._animate_hover(1.0 if self._switch_rect().contains(event.position().toPoint()) else 0.0)
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._switch_rect().contains(event.position().toPoint()):
            # 按住开关：小球变宽；超过长按阈值后才进入拖动
            self._pressed = True
            self._dragging = False
            self._animate_press(1.0)
            self._drag_timer.start()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._pressed:
            # 松开：小球恢复原形
            self._pressed = False
            self._drag_timer.stop()
            self._animate_press(0.0)
            if self._dragging:
                # 长按拖动后：吸附到最近的一侧
                checked = self._knob_pos >= 0.5
                if checked != self.isChecked():
                    self.setChecked(checked)
                self._animate_pos(1.0 if checked else 0.0)
            else:
                # 单击：直接切换开关
                self.toggle()
            self._dragging = False
            self._animate_hover(1.0 if self._cursor_in_switch() else 0.0)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        dark, accent = self._theme()
        rect = self.rect()
        sw = self._switch_rect()

        # 轨道：关闭色 -> 强调色 平滑过渡
        off = QColor(255, 255, 255, 70) if dark else QColor(0, 0, 0, 45)
        on = QColor(accent)
        t = self._tint
        bg = QColor(
            int(off.red() + (on.red() - off.red()) * t),
            int(off.green() + (on.green() - off.green()) * t),
            int(off.blue() + (on.blue() - off.blue()) * t),
            int(off.alpha() + (255 - off.alpha()) * t),
        )
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(sw, sw.height() / 2.0, sw.height() / 2.0)

        # 小球：悬停变大、按住变宽，位置在轨道内平滑移动
        knob_w, knob_h = self._knob_size()
        left, right = self._knob_range()
        center_x = left + (right - left) * self._knob_pos
        knob_x = center_x - knob_w / 2.0
        knob_y = sw.y() + (sw.height() - knob_h) / 2.0
        knob = QColor("#FFFFFF") if (self.isChecked() or dark) else QColor("#1A1A1A")
        p.setBrush(knob)
        p.drawRoundedRect(knob_x, knob_y, knob_w, knob_h, knob_h / 2.0, knob_h / 2.0)

        # 文字（左侧）
        text_color = QColor("#FFFFFF") if dark else QColor("#1A1A1A")
        p.setPen(text_color)
        p.setFont(self.font())
        p.drawText(
            QRect(0, rect.top(), max(0, sw.x() - 8), rect.height()),
            Qt.AlignVCenter | Qt.AlignLeft,
            self.text(),
        )
        p.end()


class BreathingScrollBar(QScrollBar):
    """
    Vertical scrollbar with fixed track width (10px) and animated handle
    thickness via left/right margins. On hover: 6px -> 8px thickness with
    80ms elastic easing; content width remains stable.
    """

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.setFixedWidth(10)
        self._margin = 2  # 10 - 2 - 2 = 6px handle thickness
        self._dark = True
        self._anim = QPropertyAnimation(self, b"margin")
        self._anim.setDuration(80)
        self._anim.setEasingCurve(QEasingCurve.OutBack)
        self._apply_styles()
        # 末端光晕触发：值变化时刷新，靠近底端时绘制光晕（只连一次）
        try:
            self.valueChanged.connect(self._on_value_changed)
        except Exception:
            pass
        # 惯性回弹动画：将 value 属性在滚轮事件中平滑插值
        self._inertial_anim = QPropertyAnimation(self, b"value")
        self._inertial_anim.setDuration(300)
        self._inertial_anim.setEasingCurve(QEasingCurve.OutCubic)

    # Theme hook
    def set_dark_mode(self, dark: bool):
        self._dark = bool(dark)
        self._apply_styles()

    # QProperty for animation
    def getMargin(self) -> int:
        return int(self._margin)

    def setMargin(self, value: int):
        self._margin = int(value)
        self._apply_styles()

    margin = Property(int, getMargin, setMargin)

    def enterEvent(self, event):
        super().enterEvent(event)
        self._anim.stop()
        self._anim.setStartValue(self._margin)
        self._anim.setEndValue(1)  # 10 - 1 - 1 = 8px
        self._anim.start()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._anim.stop()
        self._anim.setStartValue(self._margin)
        self._anim.setEndValue(2)  # back to 6px
        self._anim.start()

    def wheelEvent(self, e):
        # 屏蔽父类默认逻辑，使用惯性动画平滑滚动
        try:
            delta = 0
            try:
                # angleDelta().y() 正向为向上滚动
                delta = int(e.angleDelta().y())
            except Exception:
                delta = 0
            # 若无法获取 delta，则回退父类逻辑
            if delta == 0:
                e.ignore()
                try:
                    super().wheelEvent(e)
                except Exception:
                    pass
                return
            current = int(self.value())
            # angleDelta().y() 的单位是 1/8 度，标准滚轮一格 = 120。
            # 直接把 delta 当滚动量会导致一格滚轮跳 120 个数值；
            # 按 Qt 惯例换算成“每次滚动行数 × singleStep”。
            notches = delta / 120.0
            try:
                lines = int(QApplication.wheelScrollLines())
            except Exception:
                lines = 3
            if lines <= 0:
                lines = 3
            step = max(1, int(self.singleStep())) * lines
            target = current - int(round(notches * step))
            # 无有效步长时回退到父类逻辑
            if target == current:
                e.ignore()
                try:
                    super().wheelEvent(e)
                except Exception:
                    pass
                return
            # 边界约束，防止越界
            target = max(int(self.minimum()), min(int(self.maximum()), int(target)))
            self._inertial_anim.stop()
            self._inertial_anim.setStartValue(current)
            self._inertial_anim.setEndValue(target)
            self._inertial_anim.start()
            e.accept()
        except Exception:
            # 出错时保持默认行为
            try:
                super().wheelEvent(e)
            except Exception:
                pass

    def _apply_styles(self):
        # Colors tuned for subtle glow and visibility in both themes
        # 轨道微光：1px 内侧高光，水平从左到右渐隐
        groove_bg = (
            "qlineargradient(x1:0, y1:0, x2:1, y2:0, "
            "stop:0 rgba(255,255,255,10), stop:1 rgba(255,255,255,0))"
        )
        handle_bg = "rgba(0,0,0,0.35)" if not self._dark else "rgba(255,255,255,0.35)"
        self.setStyleSheet(f"""
            QScrollBar:vertical {{
                width: 10px; margin: 0px; background: transparent;
            }}
            QScrollBar::groove:vertical {{
                background: {groove_bg}; margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {handle_bg};
                border-radius: 4px;
                min-height: 20px;
                margin-left: {self._margin}px; margin-right: {self._margin}px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px; background: transparent; border: none;
            }}
        """)


    def _on_value_changed(self, v: int):
        # 靠近底端时显示光晕，其他情况关闭
        try:
            self.update()
        except Exception:
            pass

    def paintEvent(self, event):
        # 保留原样式绘制，再叠加扫光与底端径向光晕
        super().paintEvent(event)
        try:
            rect = self.rect()
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing, True)

            # 滚动扫光：1px 高亮横线，随 value() 从顶→底移动
            try:
                scan_h = 1
                rng = max(1, int(self.maximum()) - int(self.minimum()))
                frac = (float(int(self.value()) - int(self.minimum())) / float(rng)) if rng > 0 else 0.0
                if frac < 0.0: frac = 0.0
                if frac > 1.0: frac = 1.0
                scan_y = int(round(frac * max(0, rect.height() - scan_h)))
                scan_color = QColor(255, 255, 255, 40 if self._dark else 25)
                p.setPen(scan_color)
                p.drawLine(rect.left(), rect.top() + scan_y, rect.right(), rect.top() + scan_y)
            except Exception:
                pass

            # 判断是否接近底端以绘制光晕
            at_bottom = False
            try:
                at_bottom = (self.value() >= self.maximum())
                step = 0
                if hasattr(self, 'pageStep'):
                    step = max(int(self.pageStep()), int(self.singleStep()))
                if step > 0:
                    at_bottom = (self.value() >= self.maximum() - step)
            except Exception:
                at_bottom = (self.value() >= self.maximum())

            if at_bottom:
                glow_h = 6  # 光晕高度：6px
                p.setClipRect(rect.x(), rect.bottom() - glow_h + 1, rect.width(), glow_h)
                alpha = 25 if self._dark else 18
                base = QColor(255, 255, 255, alpha)
                grad = QRadialGradient(rect.width() * 0.5, rect.height(), rect.width() * 0.6)
                grad.setColorAt(0.0, base)
                grad.setColorAt(1.0, QColor(255, 255, 255, 0))
                p.setBrush(QBrush(grad))
                p.setPen(Qt.NoPen)
                p.drawRect(rect)

            p.end()
        except Exception:
            pass

class QRippleWidget(QWidget):
    """Material风格涟漪效果：点击处生成圆形扩散，持续约300ms。

    使用方式：作为按钮的子控件，按下时调用 start(global_pos)。
    """

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self._center = QPointF(0, 0)
        self._radius = 0.0
        self._alpha = 0.0
        self._radius2 = 0.0
        self._alpha2 = 0.0
        self._anim_r = QPropertyAnimation(self, b"radius")
        self._anim_a = QPropertyAnimation(self, b"alpha")
        self._anim_r.setDuration(250)
        self._anim_a.setDuration(250)
        self._anim_r.setEasingCurve(QEasingCurve.OutCubic)
        self._anim_a.setEasingCurve(QEasingCurve.OutCubic)
        # second ripple: larger but lighter and faster
        self._anim_r2 = QPropertyAnimation(self, b"radius2")
        self._anim_a2 = QPropertyAnimation(self, b"alpha2")
        self._anim_r2.setDuration(150)
        self._anim_a2.setDuration(150)
        self._anim_r2.setEasingCurve(QEasingCurve.OutCubic)
        self._anim_a2.setEasingCurve(QEasingCurve.OutCubic)
        # 只连接一次，避免每次 start() 重复绑定导致信号堆积
        self._anim_a.finished.connect(self.hide)
        self._anim_a2.finished.connect(self.hide)
        self.hide()

    # Properties for animation
    def getRadius(self) -> float:
        return float(self._radius)

    def setRadius(self, v: float) -> None:
        self._radius = float(v)
        self.update()

    radius = Property(float, getRadius, setRadius)

    def getAlpha(self) -> float:
        return float(self._alpha)

    def setAlpha(self, v: float) -> None:
        self._alpha = float(v)
        self.update()

    alpha = Property(float, getAlpha, setAlpha)

    # Second ripple properties
    def getRadius2(self) -> float:
        return float(self._radius2)

    def setRadius2(self, v: float) -> None:
        self._radius2 = float(v)
        self.update()

    radius2 = Property(float, getRadius2, setRadius2)

    def getAlpha2(self) -> float:
        return float(self._alpha2)

    def setAlpha2(self, v: float) -> None:
        self._alpha2 = float(v)
        self.update()

    alpha2 = Property(float, getAlpha2, setAlpha2)

    def start(self, global_pos) -> None:
        try:
            # Resize overlay to full button bounds and place above
            self.setGeometry(self.parent().rect())
            self.raise_()
            # Map click to local coordinates
            local = self.mapFromGlobal(global_pos)
            self._center = QPointF(float(local.x()), float(local.y()))
            # Compute end radius: farthest corner distance
            w = self.width()
            h = self.height()
            corners = [QPointF(0, 0), QPointF(w, 0), QPointF(0, h), QPointF(w, h)]
            max_r = 0.0
            for c in corners:
                dx = c.x() - self._center.x()
                dy = c.y() - self._center.y()
                d = (dx * dx + dy * dy) ** 0.5
                if d > max_r:
                    max_r = d
            # Configure animations
            self._anim_r.stop(); self._anim_a.stop()
            self._anim_r.setStartValue(0.0)
            self._anim_r.setEndValue(max_r)
            self._anim_a.setStartValue(0.35)
            self._anim_a.setEndValue(0.0)
            # second ripple: larger radius, lighter alpha
            self._anim_r2.stop(); self._anim_a2.stop()
            self._anim_r2.setStartValue(0.0)
            self._anim_r2.setEndValue(max_r * 1.5)
            self._anim_a2.setStartValue(0.35 * 0.4)
            self._anim_a2.setEndValue(0.0)
            # Show and run
            self.show()
            self._anim_r.start()
            self._anim_a.start()
            # small offset for second layer to feel like “second diffusion”
            QTimer.singleShot(80, lambda: (self._anim_r2.start(), self._anim_a2.start()))
        except Exception:
            pass

    def paintEvent(self, event):
        if (self._alpha <= 0.0 or self._radius <= 0.0) and (self._alpha2 <= 0.0 or self._radius2 <= 0.0):
            return
        try:
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing, True)
            # Radial gradient for soft edge ripple
            # Choose base color according to window theme accent; fallback to dark/light base
            try:
                w = self.window()
                dark = True
                if w is not None:
                    dark = bool(getattr(w, '_theme_dark', True))
                base = None
                if w is not None:
                    pal = w.palette()
                    try:
                        accent = pal.color(QPalette.Highlight)
                        base = QColor(accent)
                    except Exception:
                        base = None
                if base is None:
                    base = QColor(255, 255, 255) if dark else QColor(0, 0, 0)
            except Exception:
                base = QColor(255, 255, 255)
            # First layer
            if self._alpha > 0.0 and self._radius > 0.0:
                grad1 = QRadialGradient(self._center, self._radius)
                c1 = QColor(base)
                c1.setAlphaF(max(0.0, min(1.0, self._alpha)))
                c2 = QColor(base)
                c2.setAlphaF(0.0)
                grad1.setColorAt(0.0, c1)
                grad1.setColorAt(1.0, c2)
                p.setBrush(QBrush(grad1))
                p.setPen(Qt.NoPen)
                p.drawEllipse(self._center, self._radius, self._radius)
            # Second layer: larger radius, lighter alpha
            if self._alpha2 > 0.0 and self._radius2 > 0.0:
                grad2 = QRadialGradient(self._center, self._radius2)
                c3 = QColor(base)
                c3.setAlphaF(max(0.0, min(1.0, self._alpha2)))
                c4 = QColor(base)
                c4.setAlphaF(0.0)
                grad2.setColorAt(0.0, c3)
                grad2.setColorAt(1.0, c4)
                p.setBrush(QBrush(grad2))
                p.setPen(Qt.NoPen)
                p.drawEllipse(self._center, self._radius2, self._radius2)
            p.end()
        except Exception:
            pass
