"""调试面板：周期性刷新窗口标题、音乐、挂机、CPU/RAM/GPU 等数据。"""

import logging
from typing import Optional

from PySide6.QtCore import Qt, QPropertyAnimation
from PySide6.QtGui import QFontMetrics

from ..core import system as sys_core
from ..ui.design import SUCCESS, WARN, TEXT_SECONDARY, PILL_BG, DARK_PILL



class DebugMixin:
    """调试面板数据刷新与系统指标封装。"""

    def _secondary_color(self) -> str:
        try:
            getter = getattr(self, "get_secondary_grey", None)
            if callable(getter):
                return getter()
        except Exception:
            pass
        return TEXT_SECONDARY

    def _set_pill(self, key: str, text: str, color: str | None = None) -> None:
        """更新状态胶囊；深色模式使用对应表面色。"""
        lbl = (getattr(self, "debug_labels", None) or {}).get(key)
        if lbl is None:
            return
        try:
            fg = color or self._secondary_color()
            bg = DARK_PILL if bool(getattr(self, "_theme_dark", False)) else PILL_BG
            lbl.setText(text)
            lbl.setStyleSheet(
                f"background: {bg}; color: {fg}; border-radius: 8px; "
                f"padding: 1px 8px; font-size: 13px;"
            )
            try:
                lbl.adjustSize()
            except Exception:
                pass
        except Exception:
            pass

    def _set_metric_text(self, key: str, text: str, color: str | None = None) -> None:
        """更新 CPU/RAM/GPU 百分比；参考图中百分比为裸文字而非胶囊。"""
        lbl = (getattr(self, "debug_labels", None) or {}).get(key)
        if lbl is None:
            return
        try:
            fg = color or self._secondary_color()
            lbl.setText(text)
            lbl.setStyleSheet(
                f"background: transparent; color: {fg}; border: none; "
                f"font-size: 13px; font-weight: 500;"
            )
        except Exception:
            pass

    def _elide_to_label(self, label, text: str, fallback_width: int = 160) -> str:
        """按标签实际宽度省略文本，避免写死宽度导致溢出或截断过早。"""
        if not text:
            return text
        try:
            w = int(label.width())
            if w <= 24:
                w = fallback_width
            else:
                w = max(40, w - 4)
            if w < 120:
                w = min(200, int(getattr(label, "maximumWidth", lambda: 220)()))
            fm = QFontMetrics(label.font())
            shown = fm.elidedText(text, Qt.ElideRight, w)
            try:
                label.setToolTip(text if shown != text else "")
            except Exception:
                pass
            return shown
        except Exception:
            return text[:40]

    # 周期性刷新调试面板数据
    def update_debug_info(self):
        try:
            title = self.get_active_window_title() or "无"
            win_lbl = self.debug_labels.get('window')
            if win_lbl is not None:
                self._set_pill('window', self._elide_to_label(win_lbl, title))

            music = self.get_smtc_info() or "无"
            mus_lbl = self.debug_labels.get('music_title')
            if mus_lbl is not None:
                self._set_pill('music_title', self._elide_to_label(mus_lbl, music))

            idle = self.get_idle_seconds()
            self._set_pill('idle_time', self.format_duration(idle))

            # 用 getattr 兜底：初始化早期（apply_theme / 壁纸亮度回调）也可能触发本方法，
            # 那时 is_sending 尚未赋值，直接访问会让整次调试面板刷新被 except 吞掉。
            sending = bool(getattr(self, "is_sending", False))
            remaining = int(getattr(self, "_countdown_seconds", 0)) if sending else 0
            self._set_pill('next_send', f"{remaining}秒" if sending else "未启用")

            cpu = self.get_cpu_usage()
            ram = self.get_ram_usage()
            gpu = self.get_gpu_usage()
            if cpu is not None:
                self._set_metric_text('cpu_usage', f"{cpu:.0f}%")
            else:
                self._set_metric_text('cpu_usage', "N/A")
            self._set_metric_bar('cpu', cpu)
            if ram is not None:
                ram_color = WARN if ram >= 85 else self._secondary_color()
                self._set_metric_text('ram_usage', f"{ram:.0f}%", ram_color)
            else:
                self._set_metric_text('ram_usage', "N/A")
            self._set_metric_bar('ram', ram)
            if gpu is not None:
                self._set_metric_text('gpu_usage', f"{gpu:.0f}%")
            else:
                self._set_metric_text('gpu_usage', "N/A")
            self._set_metric_bar('gpu', gpu)

            # 温度信息
            if getattr(self, 'auto_temp', None) and self.auto_temp.isChecked():
                try:
                    temps = sys_core.get_temperatures()
                except Exception:
                    temps = {}
                if temps:
                    order = ['cpu', 'gpu', 'nvme', 'motherboard']
                    parts = []
                    for k in order:
                        if k in temps:
                            parts.append(f"{k.upper()}: {temps[k]:.0f}°C")
                    for k, v in temps.items():
                        if k not in order:
                            parts.append(f"{k}: {v:.0f}°C")
                    raw = ", ".join(parts)
                    self._set_pill('temperatures', self._elide_to_label(
                        self.debug_labels['temperatures'], raw, fallback_width=180))
                else:
                    self._set_pill('temperatures', "N/A")
            else:
                self._set_pill('temperatures', "未启用")

            if 'hr_status' in self.debug_labels and self.debug_labels['hr_status'] is not None:
                secondary = TEXT_SECONDARY
                try:
                    getter = getattr(self, "get_secondary_grey", None)
                    if callable(getter):
                        secondary = getter()
                except Exception:
                    pass
                dot_color = secondary
                should_breathe = False
                if getattr(self, 'auto_hr', None) and self.auto_hr.isChecked():
                    bpm = None
                    if getattr(self, 'hr_monitor', None):
                        bpm = self.hr_monitor.get_last_bpm()
                        status = self.hr_monitor.get_status_text()
                        if bpm is not None:
                            bpm_text = f"{bpm} bpm"
                            if 60 <= bpm <= 100:
                                dot_color = SUCCESS
                            elif bpm < 60:
                                dot_color = "#FFC107"
                            else:
                                dot_color = WARN
                            pill_color = dot_color
                        else:
                            bpm_text = status or "等待数据…"
                            # 失败/不可用不能画成成功绿 + 呼吸点：原来只要没有读数
                            # 就一律 SUCCESS + 呼吸，于是「连接失败」「bleak 不可用」
                            # 「订阅失败」都被渲染成健康的绿色呼吸胶囊，用户会以为
                            # 心率一切正常。只有「已连接但暂时没有数据」才算等待中。
                            if any(k in str(bpm_text) for k in ("失败", "不可用", "错误", "异常")):
                                dot_color = WARN
                                pill_color = WARN
                                should_breathe = False
                            else:
                                dot_color = SUCCESS
                                pill_color = SUCCESS
                                should_breathe = True
                    else:
                        bpm_text = "未启用"
                        dot_color = secondary
                        pill_color = secondary
                        should_breathe = False
                    self._set_pill('hr_status', bpm_text, pill_color)
                else:
                    self._set_pill('hr_status', "未启用", secondary)
                    dot_color = secondary
                    should_breathe = False

                try:
                    self.hr_dot.setStyleSheet(f"border-radius: 4px; background: {dot_color};")
                    if should_breathe:
                        if self.hr_dot_anim.state() != QPropertyAnimation.Running:
                            self.hr_dot_anim.start()
                    else:
                        if self.hr_dot_anim.state() == QPropertyAnimation.Running:
                            self.hr_dot_anim.stop()
                        self.hr_dot_fx.setOpacity(1.0)
                except Exception:
                    pass
            # 同步托盘菜单文案（开始/停止）
            self._update_tray_text()

            # 同步刷新 OSC 实时预览（时间/CPU/RAM 等动态附加信息）
            try:
                self.update_osc_preview()
            except Exception:
                pass
        except Exception as e:
            logging.error(f"Debug info update failed: {e}")

    def _set_metric_bar(self, key: str, value: Optional[float]) -> None:
        """更新 CPU/RAM/GPU 的微型进度条；无数据时隐藏。"""
        try:
            bar = getattr(self, "debug_bars", {}).get(key)
            if bar is None:
                return
            if value is None:
                bar.setValue(0)
                bar.hide()
            else:
                bar.setValue(max(0, min(100, int(round(value)))))
                bar.show()
        except Exception:
            pass

    # 获取当前前台窗口标题（供调试显示）
    def get_active_window_title(self) -> Optional[str]:
        return sys_core.get_active_window_title()

    # 获取系统空闲秒数
    def get_idle_seconds(self) -> int:
        return sys_core.get_idle_seconds()

    # 格式化时长文本
    def format_duration(self, seconds: int) -> str:
        return sys_core.format_duration(seconds)

    # 获取正在播放的音乐信息
    def get_smtc_info(self) -> Optional[str]:
        return sys_core.get_smtc_info()

    # 获取 CPU 使用率
    def get_cpu_usage(self) -> Optional[float]:
        return sys_core.get_cpu_usage()

    # 获取内存使用率
    def get_ram_usage(self) -> Optional[float]:
        return sys_core.get_ram_usage()

    # 获取 GPU 使用率
    def get_gpu_usage(self) -> Optional[float]:
        return sys_core.get_gpu_usage()
