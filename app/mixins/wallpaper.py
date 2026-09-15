"""壁纸与背景管理：系统壁纸/自定义壁纸/纯色背景的加载、亮度估算与切换持久化。"""

import ctypes
import logging
import os
import sys
from typing import Optional

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPixmap


class WallpaperMixin:
    """壁纸相关能力：加载、亮度计算、切换与持久化。"""

    # 读取系统当前壁纸路径
    def get_system_wallpaper_path(self) -> str:
        if not sys.platform.startswith('win'):
            logging.warning("Wallpaper detection only supported on Windows")
            return ""
        try:
            SPI_GETDESKWALLPAPER = 0x0073
            buf = ctypes.create_unicode_buffer(260)
            ctypes.windll.user32.SystemParametersInfoW(SPI_GETDESKWALLPAPER, 260, buf, 0)
            path = buf.value
            if path and os.path.exists(path):
                return path
        except Exception:
            pass
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop") as key:
                path, _ = winreg.QueryValueEx(key, "Wallpaper")
                if path and os.path.exists(path):
                    return path
        except Exception:
            pass
        return ""

    # 按窗口尺寸加载缩放后的系统壁纸
    def load_system_wallpaper_scaled(self, size: QSize) -> QPixmap:
        try:
            path = self.get_system_wallpaper_path()
            if path:
                pix = QPixmap(path)
                if not pix.isNull():
                    return pix.scaled(size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        except Exception:
            pass
        fallback = QPixmap(size)
        fallback.fill(QColor(120, 120, 120))
        return fallback

    # 估算壁纸平均亮度（Rec.709）
    def _compute_wallpaper_luminance(self, pix: QPixmap) -> float:
        """估算壁纸平均亮度，返回 0.0~1.0（sRGB/Rec.709 近似）。"""
        try:
            if pix.isNull():
                return 0.5
            # 缩小采样以提升性能
            sample = pix.scaled(48, 48, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            img = sample.toImage().convertToFormat(QImage.Format_RGBA8888)
            w = img.width(); h = img.height()
            total = 0.0
            for y in range(h):
                for x in range(w):
                    c = img.pixelColor(x, y)
                    # Rec.709 亮度估算
                    l = 0.2126 * c.red() + 0.7152 * c.green() + 0.0722 * c.blue()
                    total += l
            avg = total / (w * h * 255.0)
            # 限制范围
            if avg < 0.0: avg = 0.0
            if avg > 1.0: avg = 1.0
            return avg
        except Exception:
            return 0.5

    # 从壁纸中提取强调色（饱和主色调）
    def extract_accent_color_from_wallpaper(self, sample_size: int = 64) -> Optional[QColor]:
        """从壁纸中提取一个有辨识度的强调色（饱和主色调）。

        算法：缩小采样 → 用 HSV 过滤灰/白/黑像素（饱和度/亮度阈值）→
        按色调分桶统计 → 返回像素最多的色调桶的平均 RGB。

        壁纸为纯色、灰度或黑白时返回 None，由调用方回退系统强调色。
        """
        try:
            if self.wallpaper.isNull():
                return None
            sample = self.wallpaper.scaled(
                sample_size, sample_size,
                Qt.IgnoreAspectRatio, Qt.SmoothTransformation,
            )
            img = sample.toImage().convertToFormat(QImage.Format_RGB888)
            buckets: dict[int, list[QColor]] = {}
            w = img.width()
            h = img.height()
            for y in range(h):
                for x in range(w):
                    c = img.pixelColor(x, y)
                    hsv = c.toHsv()
                    if hsv.hueF() < 0.0:           # 无色相（纯灰）
                        continue
                    if hsv.saturationF() < 0.15:   # 饱和度太低
                        continue
                    if hsv.valueF() < 0.2 or hsv.valueF() > 0.85:  # 太暗/太亮
                        continue
                    key = int(hsv.hueF() * 24) % 24
                    buckets.setdefault(key, []).append(c)
            if not buckets:
                return None
            best = max(buckets.values(), key=len)
            n = len(best)
            r = sum(c.red() for c in best) // n
            g = sum(c.green() for c in best) // n
            b = sum(c.blue() for c in best) // n
            return QColor(r, g, b)
        except Exception:
            return None

    # 根据壁纸亮度更新明暗判定与文字插值动画
    def _update_wallpaper_luminance(self) -> None:
        """根据当前壁纸更新亮度与亮/暗判定。"""
        try:
            lum = self._compute_wallpaper_luminance(self.wallpaper)
            # 较为稳健的明暗分界，避免频繁抖动
            new_is_light = bool(lum >= 0.55)
            old_is_light = bool(getattr(self, '_wallpaper_is_light', False))
            self._wallpaper_is_light = new_is_light
            # 将布尔明暗改为 0→1 插值动画以驱动次要文字平滑过渡
            try:
                target = 1.0 if new_is_light else 0.0
                start = float(getattr(self, '_wallpaper_light_factor', 1.0 if old_is_light else 0.0))
                if abs(target - start) > 0.001:
                    if self._wallpaper_factor_anim is None:
                        self._wallpaper_factor_anim = QPropertyAnimation(self, b"wallpaperLightFactor")
                        self._wallpaper_factor_anim.setEasingCurve(QEasingCurve.OutCubic)
                    self._wallpaper_factor_anim.stop()
                    self._wallpaper_factor_anim.setDuration(300)
                    self._wallpaper_factor_anim.setStartValue(start)
                    self._wallpaper_factor_anim.setEndValue(target)
                    # 动画结束后刷新一次调试面板，让状态胶囊拿到新的主题色
                    if not getattr(self, '_factor_anim_connected', False):
                        try:
                            self._wallpaper_factor_anim.finished.connect(self._on_light_factor_anim_finished)
                            self._factor_anim_connected = True
                        except Exception:
                            pass
                    self._wallpaper_factor_anim.start()
                else:
                    # 目标未变化，确保因子一致
                    self.setWallpaperLightFactor(target)
            except Exception:
                pass
            # 明暗切换时刷新面板磨砂/暗遮罩（不跟动画帧）
            if new_is_light != old_is_light:
                try:
                    applier = getattr(self, "_apply_panel_contrast", None)
                    if callable(applier):
                        applier()
                except Exception:
                    pass
        except Exception:
            self._wallpaper_is_light = False
            # 失败时退回暗配色
            try:
                self.setWallpaperLightFactor(0.0)
            except Exception:
                pass

    # 亮度过渡动画结束：按新配色重画调试胶囊（不跟动画帧，避免闪动）
    def _on_light_factor_anim_finished(self) -> None:
        try:
            updater = getattr(self, "update_debug_info", None)
            if callable(updater):
                updater()
        except Exception:
            pass

    # 刷新次要文字颜色（随亮度插值）
    def _update_secondary_text_styles(self) -> None:
        try:
            getter = getattr(self, "get_secondary_grey", None)
            if callable(getter):
                secondary = getter()
            else:
                factor = float(getattr(self, '_wallpaper_light_factor', 1.0 if getattr(self, '_wallpaper_is_light', False) else 0.0))
                # 兜底：浅壁纸用深灰
                v = int(round(170 * (1.0 - factor) + 72 * factor))
                hv = f"{v:02X}"
                secondary = f"#{hv}{hv}{hv}"
        except Exception:
            secondary = "#888888"
        try:
            self.char_count.setStyleSheet(f"color: {secondary};")
            # Header 的状态/倒计时颜色由 apply_theme 统一管理
            self.osc_addr.setStyleSheet("color: #000000; background: transparent; border: none;")
        except Exception:
            pass
        # 同步调试区与工具组标题，避免浅壁纸下仍停留在旧灰
        try:
            for label in (getattr(self, "debug_labels", None) or {}).values():
                if label is None:
                    continue
                # 状态胶囊 / 指标值的完整样式由 _set_pill / _set_metric_text 维护。
                # 这里整段覆盖会擦掉背景、圆角与字重（亮度动画每帧都调用本方法，
                # 于是胶囊会一路闪成裸文字）。颜色会在下一次 debug tick 时刷新。
                if label.objectName() in ("statusPill", "metricValue"):
                    continue
                label.setStyleSheet(f"color: {secondary}; font-size: 13px;")
            for label in (getattr(self, "debug_left_labels", None) or {}).values():
                if label is not None:
                    label.setStyleSheet(f"color: {secondary};")
            hr_key = getattr(self, "hr_key_label", None)
            if hr_key is not None:
                hr_key.setStyleSheet(f"color: {secondary};")
            # 分组标题条（tool_group_titles）刻意不在这里改：它由 apply_theme()
            # 用整段规则维护「粉色底 + 圆角 + 品牌色文字」。setStyleSheet 是整体
            # 替换，这里每次亮度插值都写一遍 font-weight/color 会把
            # QWidget#toolGroupTitle 的背景与圆角规则擦掉，粉条永久变成裸文字
            # （且标题本就不该用次要灰）。
            countdown = getattr(self, "countdown_label", None)
            if countdown is not None:
                # 必须写完整规则：只写 color 会连带擦掉 apply_theme 设定的
                # font-size: 10px，字号退回继承的 14px。
                countdown.setStyleSheet(f"font-size: 10px; color: {secondary};")
            # 亮度动画结束时立刻按新配色重画胶囊，避免等到下一次 1s tick。
            # 这里不主动调用 update_debug_info()：本方法在 MainWindow.__init__
            # 早期也会被调用，那时运行状态还没准备好。
        except Exception:
            pass

    # 读取壁纸亮度因子（Qt 属性）
    def getWallpaperLightFactor(self) -> float:
        try:
            return float(self._wallpaper_light_factor)
        except Exception:
            return 0.0

    # 写入壁纸亮度因子并刷新次要文字颜色
    def setWallpaperLightFactor(self, value: float) -> None:
        try:
            v = float(value)
        except Exception:
            v = 0.0
        if v < 0.0:
            v = 0.0
        if v > 1.0:
            v = 1.0
        self._wallpaper_light_factor = v
        # 仅更新依赖次级文字颜色的控件，避免整套样式在动画每帧重建
        self._update_secondary_text_styles()

    wallpaperLightFactor = Property(float, getWallpaperLightFactor, setWallpaperLightFactor)

    # 按当前尺寸与用户偏好加载壁纸
    def load_wallpaper_for_current_size(self) -> QPixmap:
        if self.use_plain_background:
            pix = QPixmap(self.size())
            pix.fill(QColor(255, 255, 255))
            return pix
        if self.custom_wallpaper_path and os.path.exists(self.custom_wallpaper_path):
            try:
                pix = QPixmap(self.custom_wallpaper_path)
                if not pix.isNull():
                    return pix.scaled(self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            except Exception:
                pass
        return self.load_system_wallpaper_scaled(self.size())

    # 切换自定义壁纸并持久化
    def set_custom_wallpaper(self, path: Optional[str]):
        self.custom_wallpaper_path = path if path else None
        self.use_plain_background = False if path else self.use_plain_background
        self._user_plain_override = False
        self.wallpaper = self.load_wallpaper_for_current_size()
        try:
            if getattr(self, '_bg_manager', None):
                # 用户切换壁纸：启动淡入淡出与模糊过渡
                self._bg_manager.start_transition(self.wallpaper, duration_ms=300)
        except Exception:
            pass
        # 保存偏好（壁纸路径 & 纯色开关，连同其他设置一起持久化）
        self._save_settings()
        try:
            self._update_wallpaper_luminance()
        except Exception:
            pass
        self.input_panel.wallpaper = self.wallpaper
        self.history_panel.wallpaper = self.wallpaper
        self.tool_panel.wallpaper = self.wallpaper
        try:
            # 与其他面板保持一致，调试面板的壁纸也需同步
            self.debug_panel.wallpaper = self.wallpaper
        except Exception:
            pass
        self.input_panel.update_background()
        self.history_panel.update_background()
        self.tool_panel.update_background()
        try:
            self.debug_panel.update_background()
        except Exception:
            pass
        try:
            self.apply_theme()
        except Exception:
            pass
        self.update()

    # 切换纯白背景并持久化
    def set_plain_background_enabled(self, enabled: bool):
        self.use_plain_background = enabled
        self._user_plain_override = bool(enabled)
        if enabled:
            self.custom_wallpaper_path = None
        self.wallpaper = self.load_wallpaper_for_current_size()
        try:
            if getattr(self, '_bg_manager', None):
                # 纯色背景切换也采用过渡动画
                self._bg_manager.start_transition(self.wallpaper, duration_ms=300)
        except Exception:
            pass
        # 保存偏好（连同其他设置一起持久化）
        self._save_settings()
        try:
            self._update_wallpaper_luminance()
        except Exception:
            pass
        self.input_panel.wallpaper = self.wallpaper
        self.history_panel.wallpaper = self.wallpaper
        self.tool_panel.wallpaper = self.wallpaper
        try:
            # 同步调试面板的壁纸，避免背景切换时出现不一致
            self.debug_panel.wallpaper = self.wallpaper
        except Exception:
            pass
        self.input_panel.update_background()
        self.history_panel.update_background()
        self.tool_panel.update_background()
        try:
            self.debug_panel.update_background()
        except Exception:
            pass
        try:
            self.apply_theme()
        except Exception:
            pass
        self.update()

    # 启动时立即应用壁纸，避免白屏/黑屏
    def _apply_initial_wallpaper(self):
        try:
            # 保持当前用户偏好（避免强制关闭纯色背景）
            if self._user_plain_override and self.use_plain_background:
                return
            self.wallpaper = self.load_wallpaper_for_current_size()
            try:
                if getattr(self, '_bg_manager', None):
                    # 初始应用：直接设置当前壁纸，避免开场动画
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
                self.debug_panel.wallpaper = self.wallpaper
            except Exception:
                pass
            if not self.performance_mode:
                self.input_panel.set_params(blur_strength=self._default_blurs['input'])
                self.history_panel.set_params(blur_strength=self._default_blurs['history'])
                self.tool_panel.set_params(blur_strength=self._default_blurs['tool'])
                self.debug_panel.set_params(blur_strength=self._default_blurs['debug'])
            self.input_panel.update_background()
            self.history_panel.update_background()
            self.tool_panel.update_background()
            self.debug_panel.update_background()
            self.update()
        except Exception:
            pass
