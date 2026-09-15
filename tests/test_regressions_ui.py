"""回归测试：需要 Qt 的缺陷（过渡队列死锁、投影开关、设置持久化）。

不使用真实桌面环境：强制 `QT_QPA_PLATFORM=offscreen`。
没有安装 PySide6 时整个模块自动跳过。
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtGui import QColor, QPixmap, QEnterEvent, QWheelEvent
    from PySide6.QtCore import QCoreApplication, QEvent, QPointF, QPoint, Qt
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest

    _HAVE_QT = True
except Exception:  # pragma: no cover - 无 Qt 环境
    _HAVE_QT = False


_app = None


def setUpModule():
    global _app
    if _HAVE_QT and QApplication.instance() is None:
        _app = QApplication([])


def _pix(color: str, size: int = 8) -> "QPixmap":
    pm = QPixmap(size, size)
    pm.fill(QColor(color))
    return pm


@unittest.skipUnless(_HAVE_QT, "PySide6 not available")
class BackgroundTransitionTests(unittest.TestCase):
    """`set_current()` 曾用 anim.stop() 打断过渡，而 stop() 不发 finished()，
    导致 AnimationQueue._running 永久为 True、后续过渡全部堆在队列里不执行。"""

    def setUp(self):
        from app.ui.background import BackgroundManager

        self.bg = BackgroundManager(None)

    def test_set_current_does_not_wedge_queue(self):
        self.bg.set_current(_pix("red"))
        self.bg.start_transition(_pix("blue"), 300)
        self.assertTrue(self.bg._queue._running)

        self.bg.set_current(_pix("red"))  # 过渡中 resize / 切壁纸
        self.assertFalse(
            self.bg._queue._running,
            "set_current() 打断过渡后必须释放队列，否则后续过渡永久失效",
        )
        self.assertEqual(len(self.bg._queue._q), 0)

        self.bg.start_transition(_pix("blue"), 300)
        self.assertTrue(self.bg._queue._running, "新的过渡应当立刻开始")
        self.assertEqual(len(self.bg._queue._q), 0, "不应有堆积的 payload")

    def test_done_callback_called_once(self):
        calls = []
        self.bg._transition_done = lambda: calls.append(1)
        self.bg._finish_transition()
        self.bg._finish_transition()
        self.assertEqual(calls, [1], "收尾回调必须恰好调用一次")

    def test_transition_completes_and_queued_payload_runs(self):
        self.bg.set_current(_pix("red"))
        self.bg.start_transition(_pix("blue"), 20)
        self.bg.start_transition(_pix("green"), 20)
        QTest.qWait(400)

        self.assertFalse(self.bg._queue._running)
        self.assertIsNotNone(self.bg._current_wp)
        self.assertEqual(
            self.bg._current_wp.toImage().pixelColor(0, 0).name(),
            QColor("green").name(),
            "排队中的第二次过渡应当被执行",
        )


@unittest.skipUnless(_HAVE_QT, "PySide6 not available")
class ShadowToggleTests(unittest.TestCase):
    """关闭投影曾用 setGraphicsEffect(None)，Qt 会 deleteLater 掉 effect，
    使 Python 侧的 _shadow_effect 变成悬垂对象：无法重开、改参数抛 RuntimeError。"""

    def _panel(self):
        from app.ui.panels import AcrylicPanel

        panel = AcrylicPanel(_pix("gray", 64))
        panel.resize(120, 80)
        return panel

    def test_disable_keeps_effect_alive(self):
        panel = self._panel()
        panel.set_shadow_enabled(False)
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

        effect = panel.graphicsEffect()
        self.assertIsNotNone(effect, "禁用投影不应销毁 effect")
        self.assertFalse(effect.isEnabled())

    def test_set_params_after_disable_does_not_raise(self):
        panel = self._panel()
        panel.set_shadow_enabled(False)
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        panel.set_shadow_params(blur=9)  # 曾经抛 RuntimeError
        self.assertEqual(panel.shadow_blur, 9)

    def test_can_re_enable(self):
        panel = self._panel()
        panel.set_shadow_enabled(False)
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        panel.set_shadow_enabled(True)

        effect = panel.graphicsEffect()
        self.assertIsNotNone(effect, "重新开启投影必须能装回 effect")
        self.assertTrue(effect.isEnabled())


@unittest.skipUnless(_HAVE_QT, "PySide6 not available")
class SettingsPersistenceTests(unittest.TestCase):
    """插件未挂载时 `_save_settings()` 会用固定字典覆盖磁盘内容，
    把 plugins_enabled 抹掉，导致插件永远无法保持启用。"""

    def test_save_before_plugin_manager_keeps_plugin_list(self):
        from app.core import state
        from app.main_window import MainWindow

        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        prefs_file = os.path.join(tmpdir.name, state.PREFS_FILENAME)
        with open(prefs_file, "w", encoding="utf-8") as f:
            json.dump({"plugins_enabled": ["HelloPlugin"], "custom_key": 123}, f)

        with patch.object(state, "_prefs_path", return_value=prefs_file), \
                patch.object(MainWindow, "_probe_osc_async", lambda self, *a, **k: None):
            window = MainWindow()
            try:
                window._save_settings()
            finally:
                window.close()
                window.deleteLater()

        with open(prefs_file, encoding="utf-8") as f:
            saved = json.load(f)

        self.assertEqual(
            saved.get("plugins_enabled"), ["HelloPlugin"],
            "启动阶段的保存不得抹掉已启用插件列表",
        )
        self.assertEqual(saved.get("custom_key"), 123, "未知字段应被保留")
        self.assertIn("spin_interval", saved)


def _enter_event() -> "QEnterEvent":
    return QEnterEvent(QPointF(1, 1), QPointF(1, 1), QPointF(1, 1))


@unittest.skipUnless(_HAVE_QT, "PySide6 not available")
class ToggleSwitchSyncTests(unittest.TestCase):
    """`blockSignals(True); setChecked(False)` 会连驱动外观的 toggled 一起屏蔽，
    导致「启用插件失败」回滚后小球仍停在“开”的位置。"""

    def test_set_checked_with_blocked_signals_syncs_visual(self):
        from app.ui.widgets import ToggleSwitch

        switch = ToggleSwitch("")
        self.assertFalse(switch.isChecked())

        switch.blockSignals(True)
        switch.setChecked(True)
        switch.blockSignals(False)

        self.assertTrue(switch.isChecked())
        QTest.qWait(260)  # 等旋钮/轨道动画跑完
        self.assertAlmostEqual(switch.knobPos, 1.0, places=2)

    def test_set_checked_without_blocking_still_works(self):
        from app.ui.widgets import ToggleSwitch

        switch = ToggleSwitch("")
        switch.setChecked(True)
        self.assertTrue(switch.isChecked())
        QTest.qWait(260)
        self.assertAlmostEqual(switch.knobPos, 1.0, places=2)

        switch.setChecked(False)
        QTest.qWait(260)
        self.assertAlmostEqual(switch.knobPos, 0.0, places=2)


@unittest.skipUnless(_HAVE_QT, "PySide6 not available")
class ScrollWheelStepTests(unittest.TestCase):
    """`wheelEvent` 曾把 angleDelta 的 120 单位直接当成滚动量，一格滚轮跳 120 个数值。"""

    def test_one_notch_scrolls_by_lines_times_single_step(self):
        from app.ui.widgets import BreathingScrollBar

        bar = BreathingScrollBar(Qt.Vertical)
        bar.setRange(0, 1000)
        bar.setValue(500)

        lines = int(QApplication.wheelScrollLines())
        if lines <= 0:
            lines = 3
        expected_step = max(1, int(bar.singleStep())) * lines

        event = QWheelEvent(
            QPointF(5, 5), QPointF(5, 5), QPoint(), QPoint(0, 120),
            Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False,
        )
        bar.wheelEvent(event)

        target = int(bar._inertial_anim.endValue())
        self.assertEqual(target, 500 - expected_step)
        self.assertLess(abs(target - 500), 60, "一格滚轮不应跳 120 个数值")


@unittest.skipUnless(_HAVE_QT, "PySide6 not available")
class HoverCardPositionTests(unittest.TestCase):
    """`_base_pos` 只在首次 enterEvent 抓一次，布局搬动后悬停会把卡片挪回旧坐标。"""

    def test_base_position_refreshed_after_relayout(self):
        from app.ui.widgets import HoverCard

        card = HoverCard()
        card.move(11, 317)
        card.enterEvent(_enter_event())
        card.leaveEvent(QEvent(QEvent.Leave))
        QTest.qWait(260)

        card.move(11, 37)  # 模拟 resize / 翻页后的布局搬动
        card.enterEvent(_enter_event())
        card.setLift(1.0)

        self.assertLess(
            abs(card.y() - 35), 3,
            "悬停应以新的布局位置为基准上浮 2px，而不是跳回旧坐标",
        )


@unittest.skipUnless(_HAVE_QT, "PySide6 not available")
class StaticBlurCacheTests(unittest.TestCase):
    """静态模糊缓存只按控件尺寸判断，导致外观滑条与换壁纸都不生效。"""

    def test_cache_invalidates_when_blur_strength_changes(self):
        from app.ui import panels as panels_mod

        real_blur = getattr(panels_mod, "blur_pixmap", None)
        if real_blur is None:
            self.skipTest("blur_pixmap unavailable")

        panel = panels_mod.AcrylicPanel(_pix("gray", 64))
        panel.resize(120, 80)

        with patch.object(panels_mod, "blur_pixmap", side_effect=real_blur) as spy:
            panel.set_static_blur(True)
            panel.update_background()
            baseline = spy.call_count
            self.assertGreater(baseline, 0)

            panel.update_background()
            self.assertEqual(spy.call_count, baseline, "参数未变时应命中缓存")

            panel.set_params(blur_strength=40)
            panel.update_background()
            self.assertGreater(
                spy.call_count, baseline,
                "修改模糊强度后静态缓存必须失效并重绘",
            )


@unittest.skipUnless(_HAVE_QT, "PySide6 not available")
class MainWindowRegressionTests(unittest.TestCase):
    """设置对话框泄漏与投影开关漏掉调试面板。"""

    def _new_window(self):
        from app.core import state
        from app.main_window import MainWindow

        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        prefs_file = os.path.join(tmpdir.name, state.PREFS_FILENAME)

        # 必须重定向偏好文件，否则测试会覆盖用户真实的偏好配置
        patcher = patch.object(state, "_prefs_path", return_value=prefs_file)
        patcher.start()
        self.addCleanup(patcher.stop)

        probe = patch.object(MainWindow, "_probe_osc_async", lambda self, *a, **k: None)
        probe.start()
        self.addCleanup(probe.stop)

        window = MainWindow()
        self.addCleanup(window.close)
        return window

    def test_settings_dialog_does_not_accumulate(self):
        from app.dialogs.settings import SettingsDialog

        window = self._new_window()
        created = []
        original_init = SettingsDialog.__init__

        def spy_init(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            created.append(self)

        with patch.object(SettingsDialog, "__init__", spy_init), \
                patch.object(SettingsDialog, "exec", lambda self: 0):
            for _ in range(3):
                window.open_settings_dialog()

        self.assertEqual(len(created), 3)
        for dialog in created:
            self.assertTrue(
                dialog.testAttribute(Qt.WA_DeleteOnClose),
                "设置对话框必须设置 WA_DeleteOnClose，否则每次打开都会残留",
            )
        self.assertIsNone(window._settings_dialog)

    def test_shadow_toggle_covers_debug_panel(self):
        window = self._new_window()

        window.on_shadow_toggle(False, record=False)
        effect = window.debug_panel.graphicsEffect()
        self.assertIsNotNone(effect)
        self.assertFalse(effect.isEnabled(), "关闭投影时调试面板也必须关掉阴影")

        window.on_shadow_toggle(True, record=False)
        self.assertTrue(window.debug_panel.graphicsEffect().isEnabled())


if __name__ == "__main__":
    unittest.main()
