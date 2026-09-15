"""OSC 通信：消息合成、发送到 VRChat、可用性探测与结果提示。"""

from datetime import datetime
import html
import logging
import threading

from ..core.composer import compose_full_message


logger = logging.getLogger(__name__)


class OscMixin:
    """OSC 消息合成、发送与探测。"""

    # 合成最终发送文本（含附加信息）
    def compose_message(self) -> str:
        raw = self.input_edit.toPlainText()
        include_hw = getattr(self, "auto_hardware", None) and self.auto_hardware.isChecked()
        final = compose_full_message(
            raw_text=raw,
            wrap_newlines=self.auto_wrap.isChecked(),
            include_time=self.auto_time.isChecked(),
            include_window_title=self.auto_window.isChecked(),
            include_music=self.auto_music.isChecked(),
            include_idle=self.auto_idle.isChecked(),
            idle_threshold=60,
            include_cpu=include_hw and self.auto_cpu.isChecked(),
            include_ram=include_hw and self.auto_ram.isChecked(),
            include_gpu=include_hw and self.auto_gpu.isChecked(),
            include_temp=include_hw and getattr(self, 'auto_temp', None) and self.auto_temp.isChecked(),
            include_hr=getattr(self, 'auto_hr', None) and self.auto_hr.isChecked(),
            max_len=self.max_message_length,
        )
        # 统一返回字符串，避免调用方未处理 None 导致的异常
        return final or ""

    # 发送消息到 VRChat OSC，并记录历史/状态
    def send_message(self):
        try:
            # compose_message() 会解引用 auto_* 控件并调用系统指标接口，
            # 必须放在 try 内：否则组合阶段的异常会逃出 Qt 槽函数，
            # 连“发送失败”状态都更新不了。
            final = self.compose_message()
            if not final:
                return False
            sent = bool(self.osc_client and self.osc_client.send_message(final, True))
            if not sent:
                self.set_app_status("发送失败", "OSC 未发送", "error")
                return False
            # 累计历史（时间 + 摘要 + 状态），不再每次清空
            self.append_message(final)
            self.on_text_changed()
            self.set_app_status("自动发送中" if self.is_sending else "已发送", None, "success")
            return True
        except Exception as e:
            safe_err = html.escape(str(e)[:100])
            try:
                self.set_app_status("发送失败", safe_err, "error")
            except Exception:
                logger.exception("Failed to report send error: %s", e)
            return False

    # 后台线程探测 VRChat OSC 是否可用
    def _probe_osc_async(self, show_popup: bool = False) -> None:
        """Probe VRChat OSC availability without blocking the UI.

        Strategy: spawn a background thread that calls `OSCClient.probe_enabled()`
        with a 1s timeout. The result is reported via `oscProbeResult(probe_id, enabled)`.
        只有 `show_popup=True` 的那一次探测才允许弹窗；每次探测带自增 probe_id，
        避免启动探测的迟到结果误触发（或吞掉）用户触发的弹窗。
        """
        try:
            self._osc_probe_seq = int(getattr(self, "_osc_probe_seq", 0)) + 1
        except Exception:
            self._osc_probe_seq = 1
        probe_id = self._osc_probe_seq
        if show_popup:
            # 记录“允许弹窗”的那次探测序号（仅主线程读写）
            self._osc_popup_probe_id = probe_id

        def worker():
            enabled = False
            try:
                enabled = bool(self.osc_client.probe_enabled(timeout=1.0))
            except Exception:
                # 记录探测异常，但保持 UI 无阻塞
                logger.debug("OSC probe_enabled raised exception", exc_info=True)
                enabled = False

            # 仅通过跨线程 Signal 报告结果，避免后台线程直接触碰 UI
            try:
                self.oscProbeResult.emit(probe_id, enabled)
            except Exception as e:
                logger.debug(f"Emit oscProbeResult failed: {e}", exc_info=True)

        try:
            t = threading.Thread(target=worker, daemon=True)
            t.start()
        except Exception as e:
            # 线程无法启动属异常情况，记录并给出 UI 提示
            logger.exception(f"Failed to start OSC probe thread: {e}")
            try:
                self.set_app_status("OSC 探测失败", "请稍后重试", "error")
            except Exception:
                # 状态标签不可用时忽略，但错误已记录
                pass

    # 主线程处理探测结果（必要时弹窗提示）
    def _on_osc_probe_result(self, probe_id: int, enabled: bool) -> None:
        """在主线程处理 OSC 探测结果并更新 UI。

        启动时的探测只记录状态、不弹窗；只有用户点击「开始发送」触发的那次探测
        （probe_id 与 `_osc_popup_probe_id` 相同）检测到 OSC 未启用时才弹出提示。
        这样并发的探测不会互相消费弹窗令牌。
        """
        if enabled:
            return
        if getattr(self, "_osc_popup_probe_id", None) != probe_id:
            return
        self._osc_popup_probe_id = None
        self._show_osc_not_enabled_popup()

    # 弹出 OSC 未启用提示
    def _show_osc_not_enabled_popup(self) -> None:
        """提示用户启用 VRChat OSC（仅主线程调用）。"""
        try:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(
                self,
                "OSC 未启用",
                "未在 1 秒内收到 VRChat /chatbox/typing 响应。\n"
                "请打开 VRChat 设置中的 OSC 开关（Options → OSC）。",
            )
        except Exception as e:
            logger.debug(f"Showing OSC disabled message failed in main thread: {e}", exc_info=True)
