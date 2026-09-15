"""发送调度：开始/停止、定时发送、倒计时与心率监控开关。"""

import logging
import threading

from PySide6.QtCore import QThread, QTimer
from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

from ..hr import ensure_monitor_started, scan_devices


logger = logging.getLogger(__name__)


class SendingMixin:
    """自动发送调度与心率开关。"""

    def _restore_ready_status_later(self, delay_ms: int = 1800) -> None:
        """临时操作提示结束后恢复应用级“就绪”状态；自动发送时不覆盖倒计时。"""
        def _restore():
            try:
                if not bool(getattr(self, "is_sending", False)):
                    self.set_app_status("就绪", "一切正常", "normal")
            except Exception:
                pass
        try:
            QTimer.singleShot(max(0, int(delay_ms)), _restore)
        except Exception:
            pass

    # 开始/停止发送（线程安全入口）
    def on_toggle_send(self):
        try:
            app = QApplication.instance()
            if app and QThread.currentThread() != app.thread():
                # 非主线程来调用时，仅排入一次队列，避免重复排队导致竞态
                if not getattr(self, "_toggle_pending", False):
                    self._toggle_pending = True
                    # 必须用带 context 的三参重载。两参版本会把定时器建在「当前
                    # 线程」，并不能把槽派发回 GUI 线程，于是：
                    #   - 调用线程没有事件循环（普通 threading.Thread）→ 槽永不执行，
                    #     _toggle_pending 卡在 True，此后再也无法跨线程切换发送状态；
                    #   - 调用线程有事件循环（QThread + exec()）→ 槽在 worker 线程里
                    #     直接操作 Qt 控件，触发 access violation（实测崩溃栈落在
                    #     update_osc_preview → setPlainText）。
                    QTimer.singleShot(0, self, self._on_toggle_send_main)
                return
        except Exception:
            pass
        # 主线程直接执行
        self._on_toggle_send_main()

    # 主线程执行发送状态切换
    def _on_toggle_send_main(self):
        # 在主线程中统一处理状态切换，避免 UI 与计时器在不同线程变更
        try:
            should_start = False
            with self._send_lock:
                if not self.is_sending:
                    self.is_sending = True
                    should_start = True
                else:
                    self.is_sending = False

            if should_start:
                if not self.input_edit.toPlainText().strip():
                    self.set_app_status("无法发送", "消息内容不能为空", "warning")
                    with self._send_lock:
                        self.is_sending = False
                    return
                self.start_sending()
            else:
                self.stop_sending()
        finally:
            self._toggle_pending = False

    # 发送间隔变化：同步定时器周期（发送中立即生效）并刷新倒计时
    def on_interval_changed(self, seconds: int) -> None:
        """间隔滑条/微调框变化时调用，避免“界面显示新间隔、定时器仍按旧周期发送”。"""
        try:
            interval_ms = max(1, int(seconds)) * 1000
        except Exception:
            return
        try:
            timer = getattr(self, "send_timer", None)
            if timer is not None:
                if timer.interval() != interval_ms:
                    timer.setInterval(interval_ms)
                if bool(getattr(self, "is_sending", False)):
                    # 发送中：按新周期重新计时，并同步倒计时显示
                    self._countdown_seconds = max(1, int(seconds))
                    self.update_countdown_label(self._countdown_seconds)
                    timer.start()
        except Exception as e:
            logger.debug(f"Failed to apply new send interval: {e}", exc_info=True)
        try:
            self._save_settings()
        except Exception as e:
            logger.debug(f"Failed to persist send interval: {e}", exc_info=True)

    # 启动自动发送：立即发一条并启动定时器
    def start_sending(self):
        with self._send_lock:
            self.is_sending = True
        self.set_app_status("自动发送中", "正在发送消息", "info")
        self.start_btn.setText("停止发送")
        try:
            self.start_btn.setIcon(self.get_icon("stop"))
        except Exception:
            pass
        # 主按钮立即进入稳定的“停止发送”状态，不再闪过临时文案。
        try:
            self._update_tray_text()
        except Exception as e:
            logger.debug(f"Update tray text failed on start: {e}", exc_info=True)
        # 点击开始发送后异步探测 OSC：未识别到端口时弹窗提示（不阻塞发送）
        try:
            self._probe_osc_async(show_popup=True)
        except Exception as e:
            logger.debug(f"Failed to start OSC probe on send start: {e}", exc_info=True)
        interval = self.spin_interval.value()
        self.send_message()
        self.send_timer.setInterval(interval * 1000)
        self.send_timer.start()
        self._countdown_seconds = interval
        self.update_countdown_label(self._countdown_seconds)
        self.countdown_timer.start()

    # 停止自动发送并复位界面
    def stop_sending(self):
        self.send_timer.stop()
        self.countdown_timer.stop()
        with self._send_lock:
            self.is_sending = False
        self.set_app_status("就绪", "一切正常", "normal")
        self.start_btn.setText("开始发送")
        try:
            self.start_btn.setIcon(self.get_icon("send"))
        except Exception:
            pass
        # 停止后立即恢复主操作文案。
        self.countdown_label.setText("一切正常")
        try:
            self._update_tray_text()
        except Exception as e:
            logger.debug(f"Update tray text failed on stop: {e}", exc_info=True)

    # 定时器到点：发送并复位倒计时
    def on_send_timer(self):
        self.send_message()
        self._countdown_seconds = self.spin_interval.value()
        self.update_countdown_label(self._countdown_seconds)

    # 每秒刷新倒计时显示
    def on_countdown_tick(self):
        if not self.is_sending:
            return
        if self._countdown_seconds > 0:
            self._countdown_seconds -= 1
            self.update_countdown_label(self._countdown_seconds)

    # 更新倒计时标签文本
    def update_countdown_label(self, remaining: int):
        self.countdown_label.setText(f"下次发送还剩 {remaining} 秒")
        try:
            self.countdown_label.setToolTip("")
        except Exception:
            pass

    # 选择心率设备：后台扫描附近蓝牙设备，结果通过信号回到主线程
    def on_choose_device(self):
        try:
            self.set_app_status("搜索设备", "正在扫描附近蓝牙设备", "info")
        except Exception:
            pass

        def worker():
            devices = []
            try:
                devices = scan_devices(timeout=8.0)
            except Exception:
                devices = []
            try:
                # 跨线程经 Signal 回主线程，避免后台线程直接触碰 UI
                self.chooseDeviceResult.emit(devices)
            except Exception:
                pass

        try:
            t = threading.Thread(target=worker, daemon=True)
            t.start()
        except Exception as e:
            logger.exception(f"启动蓝牙扫描线程失败: {e}")
            try:
                self.set_app_status("扫描失败", "无法启动蓝牙扫描", "error")
            except Exception:
                pass

    # 主线程处理扫描结果并弹出设备选择框
    def _on_device_scan_result(self, devices):
        try:
            if not devices:
                self.set_app_status("未发现设备", "请确认蓝牙已开启", "warning")
                QMessageBox.information(self, "选择设备", "未发现可用的蓝牙设备，请确认蓝牙已开启。")
                self._restore_ready_status_later(2200)
                return
            names = [f"{d.get('name') or '(未命名)'}  ({d.get('address')})" for d in devices]
            choice, ok = QInputDialog.getItem(self, "选择设备", "检测到以下蓝牙设备：", names, 0, False)
            if not ok or not choice:
                self.set_app_status("就绪", "已取消选择设备", "normal")
                return
            addr = choice.rsplit("(", 1)[-1].rstrip(")").strip() if "(" in choice else choice.strip()
            self._connect_hr_device(addr)
        except Exception as e:
            logger.exception(f"处理设备列表失败: {e}")

    # 连接指定心率设备
    def _connect_hr_device(self, address: str):
        try:
            self.hr_monitor = ensure_monitor_started()
            self.hr_monitor.connect_to(address)
            self.set_app_status("正在连接", "心率设备", "info")
            self._restore_ready_status_later(1800)
        except Exception as e:
            logger.exception(f"连接心率设备失败: {e}")
            self.set_app_status("连接失败", "心率设备连接失败", "error")

    # 勾选/取消「心率状态」：启动或停止 BLE 监测
    def on_toggle_hr(self, enabled: bool):
        if enabled:
            try:
                self.hr_monitor = ensure_monitor_started()
                # 心率属于功能状态，不长期占用顶部应用状态。实时状态在右侧面板展示。
                if not bool(getattr(self, "is_sending", False)):
                    self.set_app_status("就绪", "一切正常", "normal")
            except Exception as e:
                logger.exception(f"启动心率监测失败: {e}")
                self.set_app_status("心率监测失败", "无法启动 BLE 监测", "error")
                self._restore_ready_status_later(2600)
        else:
            mon = getattr(self, "hr_monitor", None)
            if mon is not None:
                try:
                    # 短 join：这是主线程路径，不能让界面卡住；
                    # HeartRateMonitor.start() 会等待尚未退出的旧线程。
                    mon.stop(join_timeout=0.25)
                except TypeError:
                    # 兼容只接受无参 stop() 的实现（例如测试替身）
                    try:
                        mon.stop()
                    except Exception as e:
                        logger.debug(f"Stop heart-rate monitor failed: {e}", exc_info=True)
                except Exception as e:
                    logger.debug(f"Stop heart-rate monitor failed: {e}", exc_info=True)
                self.hr_monitor = None
            try:
                if not bool(getattr(self, "is_sending", False)):
                    self.set_app_status("就绪", "一切正常", "normal")
            except Exception:
                pass
