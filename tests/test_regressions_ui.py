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

    def test_cross_thread_toggle_is_dispatched_to_gui_thread(self):
        """非 GUI 线程调用 on_toggle_send() 必须被派发回主线程。

        曾用两参 `QTimer.singleShot(0, self._on_toggle_send_main)`：定时器建在
        「调用线程」，worker 线程没有事件循环时槽永不执行，`_toggle_pending`
        永久卡在 True，此后所有跨线程切换都被静默丢弃；若调用线程有事件循环，
        槽会在 worker 线程直接操作 Qt 控件并崩溃。
        """
        import threading

        window = self._new_window()
        window.input_edit.setPlainText("cross-thread")
        window.on_text_changed()
        with patch.object(window, "send_message", lambda: True):
            thread = threading.Thread(target=window.on_toggle_send)
            thread.start()
            thread.join()
            for _ in range(50):
                QCoreApplication.processEvents()

        self.assertFalse(
            window._toggle_pending,
            "跨线程调用后 _toggle_pending 必须被复位，否则通道永久锁死",
        )
        self.assertTrue(window.is_sending, "跨线程调用应当真的启动发送")
        window.stop_sending()

    def test_performance_mode_respects_disabled_shadow(self):
        """性能模式只能「强制关闭」阴影，重新打开时必须尊重用户的投影偏好。"""
        window = self._new_window()
        window.on_shadow_toggle(False)          # 用户主动关闭投影
        self.assertFalse(window._shadow_enabled)

        window.set_performance_mode(True)
        window.set_performance_mode(False)      # 曾经在这里被无条件重新打开
        panels = (window.input_panel, window.history_panel,
                  window.tool_panel, window.debug_panel)
        self.assertEqual(
            [p.graphicsEffect().isEnabled() for p in panels],
            [False, False, False, False],
            "用户已关闭的投影不得被性能模式开关重新打开",
        )

    def test_performance_mode_still_forces_shadow_off(self):
        window = self._new_window()
        window.on_shadow_toggle(True)
        window.set_performance_mode(True)
        panels = (window.input_panel, window.history_panel,
                  window.tool_panel, window.debug_panel)
        self.assertEqual(
            [p.graphicsEffect().isEnabled() for p in panels],
            [False, False, False, False],
            "性能模式必须强制关闭阴影",
        )

    def test_tool_group_title_stylesheet_survives_luminance_change(self):
        """亮度插值刷新次要文字颜色时，不得擦掉分组标题的粉色底与圆角。

        setStyleSheet 是整体替换，而该刷新每帧都会跑。
        """
        window = self._new_window()
        titles = getattr(window, "tool_group_titles", None) or []
        self.assertTrue(titles, "应当存在工具面板分组标题")
        window.apply_theme()
        for value in (0.2, 0.5, 0.8, 1.0):
            window.setWallpaperLightFactor(value)
        sheet = titles[0].styleSheet()
        self.assertIn("background-color", sheet, "分组标题的粉底规则被擦掉了")
        self.assertIn("border-radius", sheet, "分组标题的圆角规则被擦掉了")

    def test_countdown_label_keeps_font_size(self):
        window = self._new_window()
        window.apply_theme()
        window.setWallpaperLightFactor(0.9)
        self.assertIn(
            "font-size", window.countdown_label.styleSheet(),
            "倒计时标签的字号被亮度刷新擦掉了",
        )

    def test_button_press_animation_actually_runs(self):
        """按下缩放动画曾被 GC（QPropertyAnimation 的第二个参数是属性名）。"""
        import time

        window = self._new_window()
        button = window.start_btn
        original = button.geometry()
        window._btn_press(button)
        for _ in range(40):
            QCoreApplication.processEvents()
            time.sleep(0.005)
        pressed = button.geometry()
        window._btn_release(button)
        for _ in range(40):
            QCoreApplication.processEvents()
            time.sleep(0.005)

        self.assertLess(
            pressed.width(), original.width(),
            "按下按钮应当缩小（动画对象不能被垃圾回收）",
        )
        self.assertGreater(
            pressed.x(), 0,
            "动画基准必须是实时几何，不能是首次布局前的脏值 (0,0)",
        )
        self.assertEqual(button.geometry(), original)

    def test_hr_failure_status_is_not_success_green(self):
        """BLE 连接/订阅失败曾被渲染成健康的绿色呼吸胶囊。"""

        class _FakeMonitor:
            def __init__(self, status):
                self._status = status

            def get_last_bpm(self):
                return None

            def get_status_text(self):
                return self._status

            def stop(self, *args, **kwargs):
                pass

        window = self._new_window()
        window.auto_hr.setChecked(True)
        warn = "#F03E75"
        success = "#34B66A"
        for status, expected in (
            ("连接失败", warn),
            ("bleak 不可用", warn),
            ("订阅失败", warn),
            ("已连接", success),
        ):
            window.hr_monitor = _FakeMonitor(status)
            window.update_debug_info()
            sheet = window.debug_labels["hr_status"].styleSheet()
            self.assertIn(
                expected, sheet,
                f"状态 {status!r} 的胶囊配色不正确",
            )

    def test_blur_restores_user_setting_after_performance_mode(self):
        """退出性能模式曾把模糊写死成 6，丢弃用户设定值。"""
        window = self._new_window()
        window.on_strength_change(20)
        window.set_performance_mode(True)
        window.set_performance_mode(False)
        targets = [
            p._blur_target for p in (window.input_panel, window.history_panel,
                                     window.tool_panel, window.debug_panel)
        ]
        self.assertEqual(targets, [20, 20, 20, 20])

    def test_settings_sliders_reflect_current_appearance(self):
        """外观滑条曾硬编码 14/28/16，从不回填实际生效值。"""
        from app.dialogs.settings import SettingsDialog

        window = self._new_window()
        window.on_strength_change(20)
        window.on_alpha_change(45)
        window.on_radius_change(24)

        dialog = SettingsDialog(window)
        try:
            self.assertEqual(dialog.sld_strength.value(), 20)
            self.assertEqual(dialog.sld_alpha.value(), 45)
            self.assertEqual(dialog.sld_radius.value(), 24)
            self.assertEqual(dialog.lbl_strength.text(), "20")
        finally:
            dialog.close()
            dialog.deleteLater()

        # 构造对话框本身不得反向覆盖用户设置
        self.assertEqual(window._current_blur_strength, 20)
        self.assertEqual(window._current_white_alpha, 45)
        self.assertEqual(window._current_corner_radius, 24)

    def test_startup_blur_matches_user_setting(self):
        """启动曾用 per-panel 的 _default_blurs(24/18/12/6)，覆盖用户设定的模糊值。

        该字典在 `set_performance_mode()` 之后被应用，把刚恢复的用户值又冲掉，
        于是设置对话框显示 20、面板实际却是 24/18/12/6。
        """
        import json
        import tempfile

        from app.core import state
        from app.main_window import MainWindow

        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        prefs_file = os.path.join(tmpdir.name, state.PREFS_FILENAME)
        with open(prefs_file, "w", encoding="utf-8") as f:
            json.dump({"performance_mode": False, "blur_strength": 20}, f)

        with patch.object(state, "_prefs_path", return_value=prefs_file), \
                patch.object(MainWindow, "_probe_osc_async", lambda self, *a, **k: None):
            window = MainWindow()
        self.addCleanup(window.close)

        targets = [
            p._blur_target for p in (window.input_panel, window.history_panel,
                                     window.tool_panel, window.debug_panel)
        ]
        self.assertEqual(
            targets, [20, 20, 20, 20],
            "启动时必须沿用用户设定的模糊强度，而不是 per-panel 默认值",
        )


@unittest.skipUnless(_HAVE_QT, "PySide6 not available")
class BackgroundCompositeTests(unittest.TestCase):
    """过渡合成曾把总不透明度恒定为 0.6，整窗背景在换壁纸时泛灰。"""

    def _render(self, bg, t):
        from PySide6.QtGui import QPainter
        from PySide6.QtCore import QRect

        canvas = QPixmap(64, 64)
        canvas.fill(QColor(0, 0, 0))
        painter = QPainter(canvas)
        try:
            bg._alpha = t
            bg.render_into(painter, QRect(0, 0, 64, 64))
        finally:
            painter.end()
        return canvas.toImage().pixelColor(32, 32)

    def test_crossfade_never_reveals_background(self):
        from app.ui.background import BackgroundManager

        white = _pix("white", 64)
        bg = BackgroundManager(None)
        bg.set_current(white)
        bg.start_transition(_pix("white", 64), 300)
        self.assertTrue(bg.has_transition())

        for t in (0.0, 0.25, 0.5, 0.75, 0.99):
            color = self._render(bg, t)
            self.assertEqual(
                (color.red(), color.green(), color.blue()), (255, 255, 255),
                f"alpha={t} 时透出了底色，说明交叉淡入淡出没有盖满窗口",
            )

    def test_crossfade_blends_the_two_wallpapers(self):
        from app.ui.background import BackgroundManager

        bg = BackgroundManager(None)
        bg.set_current(_pix("red", 64))
        bg.start_transition(_pix("blue", 64), 300)
        mid = self._render(bg, 0.5)
        self.assertEqual(mid.alpha(), 255, "过渡中点不得半透明")
        self.assertGreater(mid.red(), 0, "中点应当仍含旧壁纸的红色分量")
        self.assertGreater(mid.blue(), 0, "中点应当已含新壁纸的蓝色分量")


@unittest.skipUnless(_HAVE_QT, "PySide6 not available")
class BlurTargetTests(unittest.TestCase):
    """模糊过渡曾把「动画中途的当前值」当成新目标，导致强度阶梯式衰减且不自愈；
    另外 set_params() 不停掉运行中的动画，用户设置会被旧 endValue 静默覆盖。"""

    def _panel(self, blur: int = 24):
        from app.ui.panels import AcrylicPanel

        panel = AcrylicPanel(_pix("red", 40), blur_strength=blur)
        panel.static_blur_enabled = False
        panel.resize(300, 200)
        return panel

    def _pump(self, ms: int) -> None:
        import time

        end = time.time() + ms / 1000.0
        while time.time() < end:
            QCoreApplication.processEvents()
            time.sleep(0.005)

    def test_repeated_wallpaper_changes_do_not_decay_blur(self):
        panel = self._panel(24)
        for color in ("blue", "green", "yellow", "cyan", "magenta", "gray"):
            panel.wallpaper = _pix(color, 40)
            panel.update_background()
            self._pump(120)  # 在 300ms 过渡途中再次换壁纸
        self._pump(400)      # 让最后一次过渡跑完
        self.assertEqual(
            panel.blur_strength, 24,
            "连续换壁纸不得让模糊强度衰减（曾衰减到 1）",
        )

    def test_blur_target_tracks_user_intent(self):
        panel = self._panel(24)
        panel.wallpaper = _pix("blue", 40)
        panel.update_background()
        self._pump(120)
        self.assertEqual(
            panel._blur_target, 24,
            "过渡期间意图值应保持 24，而不是被中途值污染",
        )

    def test_set_params_blur_overrides_running_transition(self):
        panel = self._panel(24)
        panel.wallpaper = _pix("blue", 40)
        panel.update_background()   # 启动 0 -> 24 过渡
        self._pump(60)
        panel.set_params(blur_strength=40)
        self._pump(600)             # 旧动画本会在此覆盖回 24
        self.assertEqual(
            panel.blur_strength, 40,
            "显式设置的模糊强度必须取消运行中的过渡动画",
        )


if __name__ == "__main__":
    unittest.main()
