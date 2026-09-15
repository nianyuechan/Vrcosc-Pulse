"""回归测试：OSC 探测弹窗令牌、发送间隔同步、心率停止、探针串行化。

这些缺陷都不需要 Qt 显示环境，因此用轻量宿主对象直接驱动 mixin。
"""

import socket
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.core import osc as osc_core
from app.core.osc import OSCClient
from app.mixins.osc import OscMixin
from app.mixins.sending import SendingMixin


class _FakeSignal:
    """替代 Qt Signal，同步记录 emit 参数。"""

    def __init__(self):
        self.calls = []

    def emit(self, *args):
        self.calls.append(args)


class _SyncThread:
    """把后台线程替换为同步执行，便于确定性断言。"""

    def __init__(self, target=None, daemon=None, **kwargs):
        self._target = target

    def start(self):
        if self._target is not None:
            self._target()


class _OscHost(OscMixin):
    def __init__(self, probe_result: bool = False):
        self.oscProbeResult = _FakeSignal()
        self.osc_client = types.SimpleNamespace(
            probe_enabled=lambda timeout=1.0: probe_result
        )
        self._osc_probe_seq = 0
        self._osc_popup_probe_id = None
        self.popups = 0

    def _show_osc_not_enabled_popup(self):
        self.popups += 1


class OscProbePopupTests(unittest.TestCase):
    """`_osc_popup_probe_id` 曾经是一个被所有并发探测共享的布尔量，
    启动探测的迟到结果会误弹（或吞掉）用户触发的提示。"""

    def _run_probe(self, host, show_popup):
        with patch("app.mixins.osc.threading.Thread", _SyncThread):
            host._probe_osc_async(show_popup=show_popup)
        # 同步线程已 emit，取出最后一次 (probe_id, enabled)
        return host.oscProbeResult.calls[-1]

    def test_stale_startup_probe_does_not_popup(self):
        host = _OscHost(probe_result=False)
        startup = self._run_probe(host, show_popup=False)
        user = self._run_probe(host, show_popup=True)

        # 启动探测的迟到结果先到
        host._on_osc_probe_result(*startup)
        self.assertEqual(host.popups, 0, "启动探测不应弹出 OSC 提示")

        # 用户触发的那次结果到齐后才提示
        host._on_osc_probe_result(*user)
        self.assertEqual(host.popups, 1)

    def test_enabled_probe_never_pops(self):
        host = _OscHost(probe_result=True)
        host._on_osc_probe_result(*self._run_probe(host, show_popup=True))
        self.assertEqual(host.popups, 0)

    def test_popup_token_consumed_once(self):
        host = _OscHost(probe_result=False)
        user = self._run_probe(host, show_popup=True)
        host._on_osc_probe_result(*user)
        host._on_osc_probe_result(*user)  # 重复投递同一结果
        self.assertEqual(host.popups, 1)

    def test_probe_ids_increase(self):
        host = _OscHost(probe_result=False)
        first = self._run_probe(host, show_popup=False)[0]
        second = self._run_probe(host, show_popup=False)[0]
        self.assertEqual((first, second), (1, 2))


class _FakeTimer:
    def __init__(self, interval=0):
        self._interval = interval
        self.started = 0

    def interval(self):
        return self._interval

    def setInterval(self, value):
        self._interval = value

    def start(self):
        self.started += 1


class _SendingHost(SendingMixin):
    def __init__(self, has_timer=True):
        self.is_sending = True
        self._countdown_seconds = 5
        self.send_timer = _FakeTimer(5000) if has_timer else None
        self.labels = []
        self.saved = 0

    def update_countdown_label(self, remaining):
        self.labels.append(remaining)

    def _save_settings(self):
        self.saved += 1


class IntervalSyncTests(unittest.TestCase):
    """改间隔曾经只写偏好、不同步 send_timer，导致倒计时与实际发送周期不一致。"""

    def test_interval_change_updates_timer_while_sending(self):
        host = _SendingHost()
        host.on_interval_changed(30)
        self.assertEqual(host.send_timer.interval(), 30000)
        self.assertEqual(host._countdown_seconds, 30)
        self.assertEqual(host.labels[-1], 30)
        self.assertEqual(host.send_timer.started, 1)
        self.assertEqual(host.saved, 1)

    def test_interval_change_when_not_sending_only_sets_timer(self):
        host = _SendingHost()
        host.is_sending = False
        host.on_interval_changed(12)
        self.assertEqual(host.send_timer.interval(), 12000)
        self.assertEqual(host.send_timer.started, 0)
        self.assertEqual(host.labels, [])

    def test_missing_timer_does_not_raise(self):
        host = _SendingHost(has_timer=False)
        host.on_interval_changed(20)  # 启动早期 send_timer 尚未创建
        self.assertEqual(host.saved, 1)

    def test_invalid_value_is_ignored(self):
        host = _SendingHost()
        host.on_interval_changed("oops")
        self.assertEqual(host.send_timer.interval(), 5000)


class _StuckThread:
    """模拟卡在 `client.connect(timeout=15)` 里的后台线程。"""

    def is_alive(self):
        return True

    def join(self, timeout=None):
        return None


class _FakeLabel:
    def __init__(self, object_name=""):
        self._name = object_name
        self.styles = []

    def objectName(self):
        return self._name

    def setStyleSheet(self, qss):
        self.styles.append(qss)


class HeartRateStopTests(unittest.TestCase):
    """`stop()` 曾无条件 `self._thread = None`：join 超时后旧线程仍在跑，
    下一次 `start()` 会 clear() 掉停止事件并起第二条 BLE 循环线程。"""

    def _monitor(self):
        from app import hr

        monitor = hr.HeartRateMonitor()
        return monitor

    def test_stop_keeps_reference_when_thread_still_running(self):
        monitor = self._monitor()
        stuck = _StuckThread()
        monitor._thread = stuck

        monitor.stop(join_timeout=0.05)

        self.assertIs(
            monitor._thread, stuck,
            "join 超时后必须保留线程引用，否则 start() 会再起一条循环线程",
        )

    def test_stop_clears_reference_when_thread_finished(self):
        monitor = self._monitor()
        monitor._thread = None
        monitor.stop(join_timeout=0.05)
        self.assertIsNone(monitor._thread)

    def test_start_does_not_replace_a_stuck_stopping_thread(self):
        from unittest.mock import patch

        monitor = self._monitor()
        stuck = _StuckThread()
        monitor._thread = stuck
        monitor._stop_event.set()

        with patch("app.hr._BLEAK_AVAILABLE", True), patch("app.hr.threading.Thread") as thread_cls:
            monitor.start()

        self.assertIs(monitor._thread, stuck)
        thread_cls.assert_not_called()

    def test_start_returns_immediately_when_already_running(self):
        from unittest.mock import patch

        monitor = self._monitor()
        stuck = _StuckThread()
        monitor._thread = stuck
        monitor._stop_event.clear()

        with patch("app.hr._BLEAK_AVAILABLE", True), patch("app.hr.threading.Thread") as thread_cls:
            monitor.start()

        self.assertIs(monitor._thread, stuck)
        thread_cls.assert_not_called()


class SecondaryTextStyleTests(unittest.TestCase):
    """亮度动画每帧重设 debug_labels 样式，会把状态胶囊的背景/圆角/字重擦掉。"""

    def _host(self):
        from app.mixins.wallpaper import WallpaperMixin

        class Host(WallpaperMixin):
            def __init__(self):
                self.char_count = _FakeLabel()
                self.osc_addr = _FakeLabel()
                self.debug_labels = {
                    "next_send": _FakeLabel("statusPill"),
                    "cpu": _FakeLabel("metricValue"),
                    "plain": _FakeLabel("debugValue"),
                }
                self.debug_left_labels = {"window": _FakeLabel()}
                self.hr_key_label = _FakeLabel()
                self.tool_group_titles = [_FakeLabel()]
                self.countdown_label = _FakeLabel()
                self._wallpaper_light_factor = 1.0
                self.debug_refreshes = 0

            def get_secondary_grey(self):
                return "#484848"

            def update_debug_info(self):
                self.debug_refreshes += 1

        return Host()

    def test_pills_and_metric_values_keep_their_style(self):
        host = self._host()
        host._update_secondary_text_styles()

        self.assertEqual(host.debug_labels["next_send"].styles, [],
                         "状态胶囊不应被整段 setStyleSheet 覆盖")
        self.assertEqual(host.debug_labels["cpu"].styles, [],
                         "指标值（字重 500）不应被覆盖")
        self.assertEqual(len(host.debug_labels["plain"].styles), 1)
        self.assertEqual(len(host.debug_left_labels["window"].styles), 1)

    def test_light_factor_animation_end_refreshes_pills(self):
        host = self._host()
        host._wallpaper_light_factor = 0.42  # 动画中途：不刷新
        host._update_secondary_text_styles()
        self.assertEqual(host.debug_refreshes, 0)

        # 动画结束回调负责按新配色重画胶囊（不在逐帧路径里调用）
        host._on_light_factor_anim_finished()
        self.assertEqual(host.debug_refreshes, 1)


class OscProbeSerializationTests(unittest.TestCase):
    """并发探测会抢绑 UDP 9001：后一次 bind 失败被误判成「OSC 未启用」。"""

    class _FakeSocket:
        def __init__(self, record, bind_error=None):
            self._record = record
            self._bind_error = bind_error

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def bind(self, addr):
            self._record["locked"] = osc_core._PROBE_LOCK.locked()
            if self._bind_error is not None:
                raise self._bind_error

        def settimeout(self, value):
            pass

        def setblocking(self, flag):
            pass

        def recvfrom(self, size):
            raise socket.timeout()

    def _client(self):
        # 必须在打补丁之前构造，否则 SimpleUDPClient 会拿到假 socket
        return OSCClient()

    def test_probe_holds_serialization_lock_while_listening(self):
        record = {}
        fake = self._FakeSocket(record)
        client = self._client()
        with patch.object(osc_core.socket, "socket", lambda *a, **k: fake):
            self.assertFalse(client.probe_enabled(timeout=0.01))
        self.assertTrue(record.get("locked"), "监听期间必须持有探测锁，避免并发抢 9001")

    def test_bind_failure_is_indeterminate_not_disabled(self):
        fake = self._FakeSocket({}, bind_error=OSError("address already in use"))
        client = self._client()
        with patch.object(osc_core.socket, "socket", lambda *a, **k: fake):
            result = client.probe_enabled(timeout=0.01)
        self.assertTrue(
            result,
            "端口被占用时无法判定状态，不应返回 False（会给用户假警告）",
        )

    def test_lock_is_released_after_probe(self):
        fake = self._FakeSocket({})
        client = self._client()
        with patch.object(osc_core.socket, "socket", lambda *a, **k: fake):
            client.probe_enabled(timeout=0.01)
        self.assertFalse(osc_core._PROBE_LOCK.locked())


class _SendHost(OscMixin):
    """compose_message 抛异常时也必须走「发送失败」而不是逃出 Qt 槽函数。"""

    def __init__(self, compose_error: bool = False):
        self.osc_client = None
        self.statuses = []
        self.appended = []
        self._compose_error = compose_error

    def compose_message(self):
        if self._compose_error:
            raise RuntimeError("boom")
        return ""

    def set_app_status(self, *args, **kwargs):
        self.statuses.append(args)

    def append_message(self, text):
        self.appended.append(text)

    def on_text_changed(self):
        pass


class SendMessageFailureTests(unittest.TestCase):
    def test_compose_exception_returns_false_and_reports(self):
        host = _SendHost(compose_error=True)
        self.assertFalse(host.send_message())
        self.assertEqual(host.statuses[-1][0], "发送失败")
        self.assertIn("boom", host.statuses[-1][1])

    def test_empty_composition_is_skipped_silently(self):
        host = _SendHost(compose_error=False)
        self.assertFalse(host.send_message())
        self.assertEqual(host.statuses, [])

    def test_missing_osc_client_reports_failure(self):
        host = _SendHost(compose_error=False)
        host.compose_message = lambda: "hello"
        self.assertFalse(host.send_message())
        self.assertEqual(host.statuses[-1][0], "发送失败")


class IconResourceTests(unittest.TestCase):
    """设置页引用的图标必须有对应 SVG，否则按钮永远是空图标。"""

    def test_referenced_icons_exist(self):
        import re
        import xml.etree.ElementTree as ET

        root = _ROOT
        icons_dir = root / "resources" / "icons"
        pattern = re.compile(r"get_icon\(['\"]([a-zA-Z_]+)['\"]\)")
        referenced = set()
        for path in (root / "app").rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            referenced.update(pattern.findall(path.read_text(encoding="utf-8")))
        self.assertTrue(referenced, "应当能在 app/ 中找到 get_icon 调用")

        missing = sorted(n for n in referenced if not (icons_dir / f"{n}.svg").exists())
        self.assertEqual(missing, [], f"缺少图标资源: {missing}")

        for name in sorted(referenced):
            ET.parse(icons_dir / f"{name}.svg")  # 解析失败会直接抛异常


if __name__ == "__main__":
    unittest.main()
