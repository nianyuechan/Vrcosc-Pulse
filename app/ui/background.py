from typing import Optional
import logging

from PySide6.QtCore import QObject, Property, QPropertyAnimation, QEasingCurve, Signal
from PySide6.QtGui import QPixmap, QPainter
from .animation import AnimationQueue


logger = logging.getLogger(__name__)


class BackgroundManager(QObject):
    """
    管理壁纸切换的淡入淡出与“模糊先出、清晰再进”过渡。

    用法：
    - 初始化时提供当前壁纸（已按窗口尺寸缩放）。
    - 调用 start_transition(new_pix) 触发 300ms InOutCubic 的 alpha 插值。
    - 在宿主窗口的 paintEvent 中调用 render_into(painter, rect) 绘制两张图的交叉淡入淡出。

    设计：
    - alpha ∈ [0,1]：0=仅旧图，1=仅新图。
    - old_blur/new_blur 仅在过渡期使用，采用一次性预计算避免逐帧计算开销。
    - 为避免瞬闪，在动画完成后才释放旧图缓存。
    """

    alphaChanged = Signal()

    def __init__(self, current_pixmap: Optional[QPixmap] = None, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._current_wp: Optional[QPixmap] = current_pixmap if current_pixmap else None
        self._old_wp: Optional[QPixmap] = None
        self._new_wp: Optional[QPixmap] = None
        self._old_blur: Optional[QPixmap] = None
        self._new_blur: Optional[QPixmap] = None
        self._alpha: float = 1.0
        self._anim: Optional[QPropertyAnimation] = None
        # 当前过渡的收尾回调（AnimationQueue 的 done）。必须保证恰好调用一次，
        # 否则队列的 _running 会永久卡在 True。
        self._transition_done: Optional[callable] = None
        self._pending: list[QPixmap] = []
        self._max_fps: int = 180
        self._last_emit_ts: float = 0.0
        self._queue = AnimationQueue(self)

        # 导入模糊工具；缺失时退化为不模糊（不阻断背景渲染）
        try:
            from utils.blur import blur_pixmap as _blur_pixmap
        except Exception:
            _blur_pixmap = None  # type: ignore
        self._blur_pixmap = _blur_pixmap  # type: ignore

    def has_transition(self) -> bool:
        return self._old_wp is not None and self._new_wp is not None and (0.0 <= self._alpha < 1.0)

    def _finish_transition(self) -> None:
        """收尾当前过渡，保证队列的 done() 恰好被调用一次。

        QAbstractAnimation.stop() 不会发出 finished() 信号，因此凡是打断动画的
        路径（set_current / 重新 start_transition）都必须显式调用本方法，
        否则 AnimationQueue._running 会永久为 True，后续过渡全部被丢弃。
        """
        done = self._transition_done
        self._transition_done = None
        if done is None:
            return
        try:
            done()
        except Exception:
            logger.debug("Transition done callback failed", exc_info=True)

    def set_current(self, pix: QPixmap) -> None:
        # 直接切换当前壁纸（用于初始化与窗口缩放），不做动画
        self._current_wp = pix
        self._old_wp = None
        self._new_wp = None
        self._old_blur = None
        self._new_blur = None
        self._alpha = 1.0
        anim = self._anim
        self._anim = None
        if anim is not None:
            try:
                anim.stop()
            except Exception:
                pass
        # stop() 不会触发 finished()：手动收尾，避免过渡队列死锁
        self._finish_transition()
        self.alphaChanged.emit()

    def start_transition(self, new_pix: QPixmap, duration_ms: int = 300) -> None:
        # 若无当前图，降级为直接设置
        if self._current_wp is None or (self._current_wp.isNull()):
            self.set_current(new_pix)
            return

        def _runner(payload: QPixmap, done: callable):
            # 记住收尾回调：set_current() 打断动画时需要手动调用它
            self._transition_done = done
            self._old_wp = self._current_wp
            self._new_wp = payload
            # 预计算轻度模糊版本（避免逐帧模糊开销）
            try:
                if self._blur_pixmap is not None:
                    self._old_blur = self._blur_pixmap(self._old_wp, 12)  # 12px 模糊半径
                    self._new_blur = self._blur_pixmap(self._new_wp, 12)
            except Exception:
                self._old_blur = None
                self._new_blur = None

            self._alpha = 0.0
            # alpha 属性动画：InOutCubic 300ms
            anim = QPropertyAnimation(self, b"alpha")
            anim.setDuration(int(duration_ms))
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.InOutCubic)
            self._anim = anim

            def _on_finished():
                # 迟到的 finished()（过渡已被 set_current() 打断并收尾）：只消费回调
                if self._anim is not anim:
                    self._finish_transition()
                    return
                # 动画完成后切换当前图并释放旧图缓存，避免瞬闪
                self._current_wp = self._new_wp
                self._old_wp = None
                self._new_wp = None
                self._old_blur = None
                self._new_blur = None
                self._alpha = 1.0
                self._anim = None
                self.alphaChanged.emit()
                # 幂等：_transition_done 可能已被 set_current 消费
                self._finish_transition()

            try:
                anim.finished.connect(_on_finished)
            except Exception:
                pass
            anim.start()

        # 提交到队列，避免多个过渡同时运行
        self._queue.submit(new_pix, _runner)

    def getAlpha(self) -> float:
        return float(self._alpha)

    def setAlpha(self, value: float) -> None:
        self._alpha = max(0.0, min(1.0, float(value)))
        # 限流发射：最多 180Hz
        import time as _t
        now = _t.time()
        interval = 1.0 / max(1, int(self._max_fps))
        if (now - self._last_emit_ts) >= interval:
            self._last_emit_ts = now
            self.alphaChanged.emit()

    alpha = Property(float, getAlpha, setAlpha)

    def render_into(self, painter: QPainter, rect) -> None:
        """在给定 painter 上绘制壁纸（并保证不污染调用方的 painter 状态）。"""
        painter.save()
        try:
            self._render_into(painter, rect)
        finally:
            painter.restore()

    def _render_into(self, painter: QPainter, rect) -> None:
        """
        在给定 painter 上绘制壁纸：
        - 过渡期：按 alpha 混合 old/new；额外叠加“旧图模糊递增、新图模糊递减”。
        - 非过渡期：绘制 current。
        注：外部应已设置裁剪圆角与渲染hint。
        """
        # 非过渡期：直接绘制当前壁纸
        if not self.has_transition():
            if self._current_wp and (not self._current_wp.isNull()):
                painter.drawPixmap(0, 0, self._current_wp)
            return

        t = float(self._alpha)
        # 旧图：总透明度 (1 - t)
        if self._old_wp and (not self._old_wp.isNull()):
            # 旧图模糊占比：随 t 递增（模糊先出）
            b_old = min(1.0, t * 1.2)
            # 采用两层混合近似连续模糊变化：清晰层与模糊层占比随 b_old 互补
            clear_ratio_old = (1.0 - b_old) * 0.6  # 清晰层最多占 60%
            blur_ratio_old = b_old * 0.6          # 模糊层最多占 60%
            base_opacity_old = (1.0 - t)

            # 清晰旧图
            if clear_ratio_old > 0.0:
                painter.setOpacity(base_opacity_old * clear_ratio_old)
                painter.drawPixmap(0, 0, self._old_wp)

            # 模糊旧图（若有缓存）
            if self._old_blur and (not self._old_blur.isNull()) and blur_ratio_old > 0.0:
                painter.setOpacity(base_opacity_old * blur_ratio_old)
                painter.drawPixmap(0, 0, self._old_blur)

        # 新图：总透明度 t
        if self._new_wp and (not self._new_wp.isNull()):
            # 新图模糊占比：起始较高，逐步递减（清晰再进）
            b_new = max(0.0, 1.0 - t * 1.2)
            blur_ratio_new = b_new * 0.6
            clear_ratio_new = (1.0 - b_new) * 0.6
            base_opacity_new = t

            # 模糊新图（若有缓存）
            if self._new_blur and (not self._new_blur.isNull()) and blur_ratio_new > 0.0:
                painter.setOpacity(base_opacity_new * blur_ratio_new)
                painter.drawPixmap(0, 0, self._new_blur)

            # 清晰新图
            if clear_ratio_new > 0.0:
                painter.setOpacity(base_opacity_new * clear_ratio_new)
                painter.drawPixmap(0, 0, self._new_wp)
