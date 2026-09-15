from typing import Optional
from PySide6.QtCore import Qt, QSize, QRectF, QTimer, QPoint, QRect, Property, QPropertyAnimation, QEasingCurve, QAbstractAnimation
from PySide6.QtGui import QPixmap, QImage, QPainter, QColor, QPainterPath
from PySide6.QtWidgets import (
    QWidget,
    QSizePolicy,
    QGraphicsBlurEffect,
    QGraphicsDropShadowEffect,
    QGraphicsScene,
    QGraphicsPixmapItem,
)

# 帧率限制器：用于合并高频刷新，最高 180Hz
try:
    from .animation import FrameLimiter  # type: ignore
except Exception:
    FrameLimiter = None  # type: ignore

from utils.blur import blur_pixmap


class UiTokens:
    # Radii
    radius_s, radius_m, radius_l = 6, 10, 14
    # Padding
    pad_s, pad_m, pad_l = 6, 12, 18
    # Blur strengths
    blur_low, blur_mid, blur_high = 8, 16, 24

    @staticmethod
    def shadow(bg: str, a: int) -> str:
        # CSS-like shadow formula (for reference in QSS-composed strings)
        return f"0 4px 12px {bg}{a}, 0 2px 4px {bg}{int(a*0.5)}"


class AcrylicPanel(QWidget):
    def __init__(
        self,
        wallpaper: QPixmap,
        blur_strength: int = 10,
        white_alpha: int = 30,
        parent: Optional[QWidget] = None,
        corner_radius: int = 16,
        border_alpha: int = 40,
        border_color: QColor = QColor(255, 255, 255, 255),
        shadow_blur: int = 24,
        shadow_offset_y: int = 4,
        shadow_alpha: int = 80,
        scrim_alpha: int = 0,
        scrim_color: Optional[QColor] = None,
    ):
        super().__init__(parent)
        # Rendering attributes to reduce flicker during rapid resizes
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_OpaquePaintEvent, False)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.wallpaper = wallpaper
        self.blur_strength = blur_strength
        self.white_alpha = white_alpha
        self.corner_radius = corner_radius
        self.border_alpha = border_alpha
        self.border_color = border_color
        self.shadow_blur = shadow_blur
        self.shadow_offset_y = shadow_offset_y
        self.shadow_alpha = shadow_alpha
        # 浅色壁纸时的暗色遮罩，提升文字对比度
        self.scrim_alpha = int(scrim_alpha)
        self.scrim_color = scrim_color if scrim_color is not None else QColor(0, 0, 0)
        self.static_blur_enabled = False
        self._cached_final = None
        # 静态模糊缓存的失效签名（尺寸/壁纸/各项外观参数/主题）
        self._cached_sig = None
        self._wallpaper_cache_key = int(wallpaper.cacheKey()) if hasattr(wallpaper, 'cacheKey') else 0
        # Blur animation (0 -> target over 300ms when wallpaper changes)
        self._blur_anim: Optional[QPropertyAnimation] = None
        # 用户意图的模糊强度。必须与 blur_strength（动画每帧写入的当前值）区分开：
        # 若把当前值当目标，过渡途中再次触发就会把中途值当成新目标，导致强度阶梯式
        # 衰减（24→14→9→6…）且永不自愈。
        self._blur_target: int = int(blur_strength)
        # White overlay alpha animation（亮度变化时的“润感”）
        self._white_anim: Optional[QPropertyAnimation] = None
        # Backbuffer for double-buffered drawing
        self._backbuffer: Optional[QPixmap] = None

        # 使用帧率限制器合并更新（最高 180Hz）
        self._frame_limiter = None
        try:
            if FrameLimiter is not None:
                self._frame_limiter = FrameLimiter(180, self)
                self._frame_limiter.set_callback(self.update_background)
        except Exception:
            self._frame_limiter = None

        # 兼容兜底：若帧率限制器不可用，使用短间隔单次计时器
        if self._frame_limiter is None:
            self._bg_update_timer = QTimer(self)
            self._bg_update_timer.setSingleShot(True)
            # 约 180Hz 的时间片（5~6ms），但仍是合并触发
            self._bg_update_timer.setInterval(6)
            self._bg_update_timer.timeout.connect(self.update_background)

        self._clip_path_cache_size = QSize()
        self._clip_path_cache_path = QPainterPath()

        self._shadow_effect = QGraphicsDropShadowEffect(self)
        self._shadow_effect.setColor(QColor(0, 0, 0, self.shadow_alpha))
        self._shadow_effect.setBlurRadius(self.shadow_blur)
        self._shadow_effect.setOffset(0, self.shadow_offset_y)
        self.setGraphicsEffect(self._shadow_effect)

    def _shadow_effect_alive(self) -> bool:
        """探测底层 C++ effect 是否仍然可用（可能已被 deleteLater）。"""
        try:
            self._shadow_effect.setBlurRadius(self._shadow_effect.blurRadius())
            return True
        except RuntimeError:
            return False
        except Exception:
            return False

    def _ensure_shadow_effect(self) -> None:
        """effect 缺失/已被销毁时重建并重新安装，保证投影可以反复开关。"""
        if self._shadow_effect_alive():
            return
        self._shadow_effect = QGraphicsDropShadowEffect(self)
        self._shadow_effect.setColor(QColor(0, 0, 0, self.shadow_alpha))
        self._shadow_effect.setBlurRadius(self.shadow_blur)
        self._shadow_effect.setOffset(0, self.shadow_offset_y)
        self.setGraphicsEffect(self._shadow_effect)

    def set_shadow_enabled(self, enabled: bool):
        """开关投影。

        注意：这里刻意不使用 `setGraphicsEffect(None)` 关闭。Qt 会对被替换掉的
        effect 调用 deleteLater()，Python 侧的 `self._shadow_effect` 随即变成
        悬垂对象，之后既无法重新安装、也无法再改参数（会抛 RuntimeError）。
        改为启用/禁用同一个 effect。
        """
        try:
            if enabled:
                self._ensure_shadow_effect()
                if self.graphicsEffect() is not self._shadow_effect:
                    self.setGraphicsEffect(self._shadow_effect)
                self._shadow_effect.setEnabled(True)
            else:
                if self.graphicsEffect() is self._shadow_effect:
                    self._shadow_effect.setEnabled(False)
                else:
                    self.setGraphicsEffect(None)
        except Exception:
            # 控件销毁过程中可能已释放底层对象，忽略
            pass

    def set_shadow_params(
        self,
        blur: Optional[int] = None,
        offset_y: Optional[int] = None,
        alpha: Optional[int] = None,
        color: Optional[QColor] = None,
    ):
        # effect 可能已被外部释放：先确保可用，避免静默抛 RuntimeError
        try:
            self._ensure_shadow_effect()
        except Exception:
            pass
        if blur is not None:
            self.shadow_blur = int(blur)
            self._shadow_effect.setBlurRadius(self.shadow_blur)
        if offset_y is not None:
            self.shadow_offset_y = int(offset_y)
            self._shadow_effect.setOffset(0, self.shadow_offset_y)
        if alpha is not None:
            self.shadow_alpha = int(alpha)
            c = QColor(self._shadow_effect.color())
            c.setAlpha(self.shadow_alpha)
            self._shadow_effect.setColor(c)
        if color is not None:
            c = QColor(color)
            c.setAlpha(self.shadow_alpha)
            self._shadow_effect.setColor(c)

    def set_params(
        self,
        blur_strength: Optional[int] = None,
        white_alpha: Optional[int] = None,
        corner_radius: Optional[int] = None,
        border_alpha: Optional[int] = None,
        border_color: Optional[QColor] = None,
        scrim_alpha: Optional[int] = None,
        scrim_color: Optional[QColor] = None,
    ):
        if blur_strength is not None:
            value = int(blur_strength)
            # 记录用户意图，并取消正在运行的过渡动画：动画对象是长期复用的，
            # 若不停掉，它接下来每一帧仍会写 blurStrength，最终停在旧 endValue 上，
            # 用户刚设的值会被静默覆盖（实测设为 40、600ms 后变回 24）。
            self._blur_target = value
            try:
                if self._blur_anim is not None:
                    self._blur_anim.stop()
            except Exception:
                pass
            self.setBlurStrength(value)
        if white_alpha is not None:
            target = int(white_alpha)
            # 亮度变化时 white_alpha 采用 300ms 动画插值并轻微“闪润”
            try:
                current = int(self.white_alpha)
            except Exception:
                current = target
            if target != current:
                if self._white_anim is None:
                    self._white_anim = QPropertyAnimation(self, b"whiteAlpha")
                    self._white_anim.setEasingCurve(QEasingCurve.OutCubic)
                self._white_anim.stop()
                self._white_anim.setDuration(300)
                self._white_anim.setStartValue(current)
                # 关键帧：在 70% 处略微超过目标，以制造“润感”闪一下（视觉很轻）
                overshoot = min(target + 6, 255)
                self._white_anim.setKeyValueAt(0.70, overshoot)
                self._white_anim.setEndValue(target)
                self._white_anim.start()
            else:
                # 无变化时按常规路径
                self.white_alpha = target
        if corner_radius is not None:
            self.corner_radius = int(corner_radius)
        if border_alpha is not None:
            self.border_alpha = int(border_alpha)
        if border_color is not None:
            self.border_color = border_color
        if scrim_alpha is not None:
            self.scrim_alpha = int(scrim_alpha)
        if scrim_color is not None:
            self.scrim_color = QColor(scrim_color)
        self.schedule_update_background()

    # QProperty for animating blur strength smoothly
    def getBlurStrength(self) -> int:
        return int(self.blur_strength)

    def setBlurStrength(self, value: int) -> None:
        try:
            self.blur_strength = int(value)
        except Exception:
            self.blur_strength = 0
        # 动画步触发刷新：通过帧率限制器合并，避免过高频刷新
        self.schedule_update_background()

    blurStrength = Property(int, getBlurStrength, setBlurStrength)

    # QProperty for animating corner radius smoothly
    def getCornerRadius(self) -> int:
        return int(self.corner_radius)

    def setCornerRadius(self, value: int) -> None:
        try:
            self.corner_radius = int(value)
        except Exception:
            # Fallback to safe int
            self.corner_radius = 0
        # 动画步触发刷新：通过帧率限制器合并
        self.schedule_update_background()

    cornerRadius = Property(int, getCornerRadius, setCornerRadius)

    # QProperty for animating white overlay alpha smoothly
    def getWhiteAlpha(self) -> int:
        return int(self.white_alpha)

    def setWhiteAlpha(self, value: int) -> None:
        try:
            self.white_alpha = int(value)
        except Exception:
            self.white_alpha = 0
        # 每个动画步刷新，通过帧率限制器合并，减少多动画并发时的开销
        self.schedule_update_background()

    whiteAlpha = Property(int, getWhiteAlpha, setWhiteAlpha)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.schedule_update_background()

    def schedule_update_background(self):
        try:
            if self._frame_limiter is not None:
                self._frame_limiter.request()
            else:
                self._bg_update_timer.start()
        except Exception:
            try:
                self.update_background()
            except Exception:
                pass

    def moveEvent(self, event):
        super().moveEvent(event)
        self.schedule_update_background()

    def _static_blur_signature(self, rect):
        """静态模糊缓存的失效签名。

        任何会影响最终渲染结果的输入变化都必须体现在这里，否则静态模糊模式下
        “模糊强度/白色遮罩/圆角/边框/壁纸”等改动都会继续显示旧图。
        """
        try:
            wp_key = int(self.wallpaper.cacheKey()) if hasattr(self.wallpaper, 'cacheKey') else self._wallpaper_cache_key
        except Exception:
            wp_key = self._wallpaper_cache_key
        try:
            w = self.window()
            if w is not None and w is not self:
                p = self.mapTo(w, QPoint(0, 0))
                origin = (int(p.x()), int(p.y()))
            else:
                origin = (0, 0)
            dark = bool(getattr(w, '_theme_dark', True))
        except Exception:
            origin = (0, 0)
            dark = True
        try:
            border_color = str(self.border_color.name())
        except Exception:
            border_color = str(self.border_color)
        try:
            scrim_color = str(self.scrim_color.name())
        except Exception:
            scrim_color = str(self.scrim_color)
        return (
            int(rect.width()), int(rect.height()),
            wp_key, origin, dark,
            int(self.blur_strength), int(self.white_alpha),
            int(self.corner_radius), int(self.border_alpha), border_color,
            int(self.scrim_alpha), scrim_color,
        )

    def update_background(self):
        # Detect wallpaper change to trigger dynamic blur animation
        try:
            key = int(self.wallpaper.cacheKey()) if hasattr(self.wallpaper, 'cacheKey') else self._wallpaper_cache_key
        except Exception:
            key = self._wallpaper_cache_key
        wallpaper_changed = (key != self._wallpaper_cache_key)
        if wallpaper_changed:
            self._wallpaper_cache_key = key
            if not self.static_blur_enabled:
                try:
                    # Prepare animation from 0 -> current target over 300ms
                    # 目标取「用户意图值」而不是 blur_strength：后者是动画每帧写入的
                    # 当前值，过渡途中再触发会读到中途值，造成强度持续衰减。
                    target_blur = int(self._blur_target)
                    if self._blur_anim is None:
                        self._blur_anim = QPropertyAnimation(self, b"blurStrength")
                        self._blur_anim.setEasingCurve(QEasingCurve.OutCubic)
                    # 已在向同一目标过渡时直接返回：避免每次换壁纸都从 0 重来
                    # （那会造成闪烁，也会让连续 resize 反复重启过渡）。
                    try:
                        running = self._blur_anim.state() == QAbstractAnimation.State.Running
                        end = int(self._blur_anim.endValue() or 0)
                    except Exception:
                        running, end = False, -1
                    if running and end == target_blur:
                        return
                    self._blur_anim.stop()
                    # Start from 0 for a glass-like live blur transition
                    self.setBlurStrength(0)
                    self._blur_anim.setDuration(300)
                    # 分段“阶梯”：0→6→15→目标，先快后慢
                    # 若目标小于分段值，按比例缩放
                    step1 = int(round(target_blur * (6.0 / 24.0)))
                    step2 = int(round(target_blur * (15.0 / 24.0)))
                    # 关键帧设置：时间分布偏向前半段快速推进
                    self._blur_anim.setKeyValueAt(0.0, 0)
                    self._blur_anim.setKeyValueAt(0.35, step1)
                    self._blur_anim.setKeyValueAt(0.70, step2)
                    self._blur_anim.setEndValue(target_blur)
                    self._blur_anim.start()
                    # Skip immediate rendering; animation will drive updates
                    return
                except Exception:
                    pass
        if self.wallpaper.isNull():
            return
        rect = self.rect()
        if rect.isEmpty():
            return
        # 预构建圆角裁剪路径（抗锯齿）
        path = QPainterPath()
        path.addRoundedRect(QRectF(rect.adjusted(0, 0, -1, -1)), self.corner_radius, self.corner_radius)

        sig = self._static_blur_signature(rect) if self.static_blur_enabled else None
        if self.static_blur_enabled and self._cached_final is not None and self._cached_sig == sig:
            final = self._cached_final
        else:
            target = QPixmap(rect.size())
            target.fill(Qt.transparent)
            painter = QPainter(target)
            painter.setRenderHint(QPainter.Antialiasing)
            # Copy the correct wallpaper slice aligned to the window coordinates
            try:
                w = self.window()
                origin = QPoint(0, 0)
                if w is not None and w is not self:
                    origin = self.mapTo(w, QPoint(0, 0))
                region = QRect(origin.x(), origin.y(), rect.width(), rect.height())
                slice_pix = self.wallpaper.copy(region)
            except Exception:
                slice_pix = self.wallpaper.copy(rect)
            painter.drawPixmap(0, 0, slice_pix)
            painter.setOpacity(self.white_alpha / 255.0 if self.white_alpha <= 255 else self.white_alpha / 100.0)
            painter.fillRect(rect, QColor(255, 255, 255, 255))
            # 浅色壁纸：叠一层暗色遮罩，避免浅灰文字被冲淡
            if self.scrim_alpha > 0:
                sc = QColor(self.scrim_color)
                sc.setAlpha(max(0, min(255, int(self.scrim_alpha))))
                painter.setOpacity(1.0)
                painter.fillRect(rect, sc)
            painter.end()

            blurred = blur_pixmap(target, self.blur_strength)
            # Build into backbuffer first to avoid tearing
            self._backbuffer = QPixmap(rect.size())
            self._backbuffer.fill(Qt.transparent)
            painter = QPainter(self._backbuffer)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            painter.setClipPath(path)
            painter.drawPixmap(0, 0, blurred)
            painter.setOpacity(1.0)
            # Border uses configurable color and alpha
            bc = QColor(self.border_color)
            bc.setAlpha(self.border_alpha)
            painter.setPen(bc)
            painter.drawRoundedRect(rect.adjusted(0, 0, -1, -1), self.corner_radius, self.corner_radius)
            # Inner glow: 1px on the inside with 20% opacity
            try:
                w = self.window()
                dark = True
                if w is not None:
                    dark = bool(getattr(w, '_theme_dark', True))
                # 内侧柔光仅用于勾出卡片边缘。浅色模式不再使用深色内描边，
                # 避免右侧/底部出现明显黑灰边。
                glow_alpha = int((0.14 if dark else 0.10) * 255)
                glow_color = QColor(235, 242, 255, glow_alpha) if dark else QColor(255, 255, 255, glow_alpha)
                painter.setPen(glow_color)
                painter.drawRoundedRect(rect.adjusted(1, 1, -2, -2), self.corner_radius, self.corner_radius)
            except Exception:
                pass
            painter.end()

            final = self._backbuffer
            if self.static_blur_enabled:
                self._cached_final = final
                self._cached_sig = sig

        self._final_pixmap = final
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        try:
            if hasattr(self, '_final_pixmap') and isinstance(self._final_pixmap, QPixmap):
                painter = QPainter(self)
                painter.setRenderHint(QPainter.Antialiasing, True)
                painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
                rect = self.rect()
                path = QPainterPath()
                path.addRoundedRect(QRectF(rect.adjusted(0, 0, -1, -1)), self.corner_radius, self.corner_radius)
                painter.setClipPath(path)
                # 按当前 rect 缩放绘制：_final_pixmap 可能还是 resize 前的尺寸
                # （重绘由帧限制器推迟若干毫秒），直接 drawPixmap(0, 0, pix) 会
                # 留下未绘制的空洞（实测 resize 后大面积 alpha=0）。
                painter.drawPixmap(rect, self._final_pixmap, self._final_pixmap.rect())
                # 额外 1px 内侧暗阴影，增强“凹陷”立体感
                try:
                    w = self.window()
                    dark = True
                    if w is not None:
                        dark = bool(getattr(w, '_theme_dark', True))
                    shadow_color = QColor(0, 0, 0, 30 if dark else 20)
                    painter.setPen(shadow_color)
                    painter.drawRoundedRect(rect.adjusted(2, 2, -2, -2), self.corner_radius, self.corner_radius)
                except Exception:
                    pass
                painter.end()
        except Exception:
            pass

    def set_static_blur(self, enabled: bool):
        self.static_blur_enabled = bool(enabled)
        if not enabled:
            self._cached_final = None
            self._cached_sig = None


