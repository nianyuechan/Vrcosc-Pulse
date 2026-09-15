# Review Findings (th4-2 snapshot)

Reviewed: Python/PySide6 "VRChat Status Hub" app under `th4-2` (static analysis;
runtime terminal unavailable this session, so no compile/run verification).

## Previously reported issues — now VERIFIED FIXED in th4-2

- `app/core/system.py` no longer hardcodes `HAS_VRCHATMSG = False`; the flag is set
  `True` inside the successful `vrchatmsg` import and `False` in the except branch.
- `app/hr.py` `ensure_monitor_started()` now always calls `_GLOBAL_MONITOR.start()`,
  and `start()` is idempotent and restartable after `stop()` (thread replaced,
  stop-event cleared).
- `app/mixins/osc.py` `send_message()` now checks the boolean from
  `OSCClient.send_message()`, shows "消息发送失败（OSC 未发送）" and returns False
  on failure; history is only appended on success.
- `plugins/manager.py` `_check_dependencies()` now treats an absent dependency
  (not a known plugin, `find_spec` fails) as missing and returns an install hint.
- `VRCOSC_Pulse.spec` uses `pathex=[SPECPATH]` instead of the hardcoded
  `c:\Users\14036\Desktop\th4`.

## Fixed in this pass (VRCOSC Pulse copy)

1. **Heart-rate toggle wired** — `auto_hr.toggled` now connects to
   `SendingMixin.on_toggle_hr`, which starts/stops the BLE monitor.
2. **`VRCOSC_Pulse.spec` datas** ship `resources/fonts` and `resources/icons` (includes
   `check.svg`) instead of only `.keep` placeholders.
3. **Prefs write is atomic** — `save_prefs` writes a temp file then `os.replace`.
4. **`QRippleWidget` signal re-connect removed** — `finished → hide` is connected
   once in `__init__`, not on every press.
5. **HR `start()`/`stop()` race** — `start()` waits for a stopping thread to exit
   before clearing `_stop_event` and spawning a new loop.
6. **Startup console respects prefs** — console visibility follows saved
   `console_toggle` instead of always hiding.
7. **Redundant debug-panel construction** — `_create_debug_labels` no longer
   builds HR dot / left labels a second time.
8. **`requirements.txt` added** — required vs optional deps listed.
9. **Product rename** — window title, in-app labels, tray tooltip, and PyInstaller
   exe name are `VRCOSC Pulse`. The prefs filename was left as
   `.vrc_qt_prefs.json` at the time to preserve existing user settings; that
   decision was later reversed — see the rename pass at the end of this file.
10. **Unit tests added** — `tests/` covers composer, HR parse, prefs atomic I/O,
    and plugin dependency checks (stdlib `unittest`, 20 cases).
11. **Cleanup** — removed `build/` and all `__pycache__`; root `__init__.py` no
    longer references a non-existent `vrc_qt` package.
12. **Light-wallpaper readability** — secondary text no longer brightens to
    `#E6E6E6` on light wallpapers (that made debug/tools unreadable). Secondary
    grey is theme-aware; debug left-column keys follow it; AcrylicPanel gained a
    dark `scrim_alpha` for dark-UI + light wallpaper, and light-UI gets a
    stronger milk-white frosted overlay. Contrast re-applies when luminance
    flips and after performance-mode resets.
13. **Debug panel layout** — temperatures row no longer blanks when the toggle
    is off (shows「未启用」); GPU missing value uses `N/A` like CPU/RAM; window/
    music/temps elide to the real label width instead of a hardcoded 220px;
    keys are left-aligned (CPU/RAM/GPU share a left edge with Chinese keys);
    metric % is fixed-width and the bar stretches to fill the row; HR bullet
    sits with「心率」left-aligned; content no longer leaves a key–value canyon.

## Fixed in the bug-hunt pass (R6)

Full static read of `app/`, `plugins/`, `utils/` plus offscreen PySide6 6.10
reproductions. Five defects were reproduced with scripts before being fixed,
and each now has a regression test.

1. **Wallpaper transition queue deadlock** (`app/ui/background.py`) —
   `set_current()` interrupted a running fade with `QPropertyAnimation.stop()`,
   which does *not* emit `finished()`, so the queue's `done()` never ran and
   `AnimationQueue._running` stayed `True` forever. Every later
   `start_transition()` was appended and never executed, permanently killing
   wallpaper fading after any resize during a 300 ms fade. `set_current()` and
   the new idempotent `_finish_transition()` now guarantee the callback fires
   exactly once; a late `finished()` is ignored.
2. **Shadow effect dangled after being switched off** (`app/ui/panels.py`) —
   `set_shadow_enabled(False)` called `setGraphicsEffect(None)`, and Qt
   `deleteLater()`s the replaced effect, leaving `self._shadow_effect` an
   invalid C++ object: re-enabling installed nothing and every later
   `set_shadow_params()` raised `RuntimeError` (swallowed). Now the same effect
   is enabled/disabled instead, `_ensure_shadow_effect()` rebuilds it if it was
   destroyed elsewhere, and `set_shadow_params()` no longer raises.
3. **`plugins_enabled` erased on every startup** (`app/main_window.py`,
   `app/core/state.py`) — `_save_settings()` writes a fixed dict and only
   included the plugin list when `plugin_manager` was attached; the first save
   happens inside `MainWindow.__init__`, before `main.py` attaches the manager,
   and `save_prefs()` overwrites the file verbatim. The key was deleted from
   disk on every launch and plugins never stayed enabled. Now the pre-loaded
   list is preserved and the write merges with the on-disk dict.
4. **Changing the send interval did not affect the timer** (`app/mixins/sending.py`,
   `app/main_window.py`) — `send_timer.setInterval()` only ran in
   `start_sending()`, while `on_send_timer()` re-seeded the countdown from the
   *current* spinbox, so the countdown lied about the real cadence. The new
   `on_interval_changed()` syncs the timer (and restarts it) while sending.
5. **Stale OSC probe popped a bogus “OSC 未启用” modal** (`app/mixins/osc.py`,
   `app/main_window.py`) — `_osc_popup_wanted` was a single flag shared by all
   concurrent probes, so the startup probe's late result could both fire the
   popup and consume the token belonging to the user-triggered probe (a probe
   that merely failed to bind UDP 9001 also reads as “disabled”). Each probe now
   carries an incrementing `probe_id` and only the matching probe may pop
   (`oscProbeResult` is now `Signal(int, bool)`).

Also fixed while in `app/ui/background.py`: `render_into()` left the caller's
painter opacity modified (the host gradient / inner shadow were drawn at ~9 %
strength mid-fade); it now saves and restores the painter state.

Known limitation left as-is: two probes that overlap still fight over UDP 9001
(the second `bind()` fails and reports “OSC 未启用”). The popup token no longer
misfires, but the probe itself can still return a false negative.

*Resolved in R8 — see item 16 below.*

## Fixed in the backlog pass (R8)

## Fixed in the backlog pass (R7)

Second batch, covering the remaining interactive defects found by the same
review. All verified with offscreen repros; regression tests added.

6. **`get_option_style()` used a PEP 701 nested-quote f-string**
   (`app/mixins/theme.py:600-601`) — `f"border-color: {"rgba(...)" if dark else "#D2D8E2"}; "`
   only parses on CPython ≥ 3.12. On 3.10/3.11 the module is a `SyntaxError` and
   the app cannot start at all. The conditional values are now pre-computed
   locals; `requirements.txt` documents the Python floor and the rule.
7. **Static-blur cache keyed only on widget size** (`app/ui/panels.py`) — the
   cache was only invalidated by `set_static_blur(False)` or a resize, so the
   blur-strength / white-overlay / corner-radius sliders and wallpaper switches
   did nothing while static blur was on. Replaced with
   `_static_blur_signature()` covering size, wallpaper cache key, slice origin,
   theme, blur/white/corner/border/scrim parameters.
8. **`SettingsDialog` leaked on every open** (`app/main_window.py`) — a parented
   `QDialog` survives a dropped Python reference, so each open left a whole
   dialog (pages, sliders, plugin-toggle connections) alive. Now
   `WA_DeleteOnClose` is set, the reference is stored and cleared, and the
   previous dialog is closed/`deleteLater()`d before a new one is built.
9. **`BreathingScrollBar.wheelEvent` treated the 120-unit wheel delta as a
   scroll amount** (`app/ui/widgets.py`) — one notch jumped 120 units. Now
   normalised to `angleDelta/120 × wheelScrollLines × singleStep`, matching a
   stock `QScrollBar` (measured: both 497 after one notch from 500).
   Also removed a duplicated `valueChanged` connection.
10. **`ToggleSwitch` desynced when `setChecked` was called with signals
    blocked** (`app/ui/widgets.py`) — `blockSignals(True)` also suppressed the
    `toggled` signal that drives the knob/tint animation, so a failed plugin
    enable left the switch drawn as ON. `setChecked` is now overridden to sync
    the visuals when signals are blocked (the settings dialog needs no change).
11. **`HoverCard` hovered to a stale position** (`app/ui/widgets.py`) — the
    `_base_pos` snapshot was taken once on first `enterEvent`, so after a
    relayout the next hover teleported the card back to its old coordinates.
    The base position is re-read on every enter while the card is not lifted.
12. **`On_shadow_toggle` skipped the debug panel** (`app/mixins/theme.py`) —
    `_apply_panel_contrast()` did touch it, so the debug card kept a drop shadow
    after the shadow was switched off.
13. **Luminance animation wiped the debug pills’ styling**
    (`app/mixins/wallpaper.py`) — the per-frame handler re-styled every
    `debug_labels` entry with `color: …; font-size: 13px;`, destroying the
    background/border-radius/font-weight set by `_set_pill` /
    `_set_metric_text`. Those labels are now skipped; the pill colours are
    refreshed once via the new `_on_light_factor_anim_finished()` callback
    instead of on every frame.
14. **`hr_monitor.stop()` could orphan a live BLE loop**
    (`app/hr.py`, `app/mixins/sending.py`) — `stop()` always did
    `self._thread = None` even when the join timed out, so the next `start()`
    cleared the stop event and spawned a second BLE loop thread for the same
    device. `stop(join_timeout=…)` now keeps the reference while the thread is
    alive and `start()` waits for it instead of duplicating; the UI path uses a
    0.25 s timeout so unchecking 心率状态 no longer freezes the window.
15. **`update_debug_info()` aborted during early startup** (`app/mixins/debug.py`)
    — `self.is_sending` / `self._countdown_seconds` were accessed unguarded, so a
    debug-panel refresh triggered before those attributes existed (surfaced while
    wiring #13) aborted the whole update and logged
    `'MainWindow' object has no attribute 'is_sending'`. Now read via `getattr`.

## Fixed in the backlog pass (R8)

Final batch: the remaining reported items plus dead-code removal.

16. **Overlapping OSC probes fought over UDP 9001** (`app/core/osc.py`) — the
    probe needs to *own* `127.0.0.1:9001` while listening, so a second concurrent
    probe failed to bind and reported “OSC 未启用”. Probes are now serialized by
    a module-level lock, and an unusable port is treated as **indeterminate**
    (returns True) instead of disabled — the probe only decides whether to nag
    the user, so it must not raise a warning it cannot back up.
17. **`send_message()` composed outside the try** (`app/mixins/osc.py`) — any
    exception from `compose_message()` (it dereferences the `auto_*` widgets and
    calls the system-metric backends) escaped the Qt slot, so even the
    「发送失败」status never appeared. Composition, sending and history updates
    now share one try/except.
18. **Dead code removed** — `UILayoutManager.create_header_layout()` (never
    called; it would have overwritten `main_window.start_btn` with an unwired
    button), the unused `music_artist` debug label, `SettingsDialog._wrap_card()`
    (every page uses `_wrap_card_layout`), and `AnimatedCardOverlay`
    (`app/ui_components.py`) which was constructed on every startup and never
    read — `main_window._history_overlay` had no consumer. The module and its
    import were deleted.
19. **「恢复默认」did not reset the send interval** (`app/dialogs/settings.py`) —
    `on_reset_defaults()` reset the appearance sliders and checkboxes but left
    `sld_interval` alone. It now returns to 30 s.
20. **Three icons had no resource** (`resources/icons/`) — `get_icon('refresh')`
    / `'image'` / `'monitor'` fell through to `QIcon.fromTheme`, which is always
    null on Windows, so 恢复默认 / 选择壁纸 / 使用系统壁纸 rendered icon-less.
    Added brand-styled `refresh.svg`, `image.svg`, `monitor.svg`.
21. **Startup paid for a system accent it immediately discards**
    (`app/main_window.py`, `app/mixins/theme.py`) — `__init__` called
    `get_system_accent_color()` (a DWM read that can fall back to a wallpaper
    pixel scan) and `apply_theme()` overwrote it with the brand pink moments
    later. The attribute is now seeded with `BRAND` directly and the unreachable
    `on_system_settings_change()` handler was deleted.

## Remaining / new issues (severity-ordered)

### Low
1. ~~**Docs residual** — historical notes in `findings.md`/`progress.md` still name
   the old product.~~ **Closed** in the rename pass below.
2. **Plugin dependency resolution** still treats a *disabled* known plugin as a
   soft miss with a hint (by design); there is no auto-enable path.
3. ~~**Prefs path** remains `~/.vrc_qt_prefs.json` (compat).~~ **Closed** — the
   file is now `~/.vrcosc_pulse_prefs.json` with an automatic one-shot migration
   from the legacy name.
4. **System accent readers retained but unused** — `get_system_accent_color()`
   / `_read_system_accent_color()` (and `extract_accent_color_from_wallpaper()`)
   are kept for a possible future “follow the system accent” option; the app
   deliberately pins the brand pink (`apply_theme`). They are no longer called on
   the startup path.

## Test gaps
- No plugin activation-order integration test with real local plugin modules.

### Closed in the R8 pass
- Osc probe/send paths now covered: `probe_enabled()` holds the serialization
  lock while listening, releases it afterwards, and treats an unusable UDP 9001
  as *indeterminate* (returns True) rather than “OSC 未启用”;
  `send_message()` returns False and reports「发送失败」when composition itself
  raises; every `get_icon('…')` name in `app/` has a matching SVG that parses.
- `tests/test_regressions_core.py`: 21 cases (R6 8 + R7 6 + R8 7).

### Closed in the R6 bug-hunt pass
- `tests/test_regressions_core.py` (8 cases) — stale/duplicate OSC probe results
  must not pop the modal; interval changes sync `send_timer` and survive a
  missing timer.
- `tests/test_regressions_ui.py` (7 cases, offscreen Qt, auto-skips without
  PySide6) — transition queue must not wedge after `set_current()` and queued
  payloads must still run; the panel shadow must survive a disable/enable cycle
  and keep accepting new params; `_save_settings()` must preserve
  `plugins_enabled` and unknown keys when called before the plugin manager
  exists.
- Suite total: 20 → 35 cases, all passing under
  `python -m unittest discover -s tests -t .`.

### Added in the R7 backlog pass
- `tests/test_regressions_core.py` — `HeartRateMonitor.stop()` must keep the
  thread reference while it is still alive and `start()` must never spawn a
  second loop thread; the luminance handler must not re-style pill / metric
  labels but the animation-end callback must refresh the debug panel.
- `tests/test_regressions_ui.py` — `ToggleSwitch` keeps its knob in sync when
  `setChecked` is called with signals blocked; one wheel notch scrolls by
  `lines × singleStep` (not 120 units); `HoverCard` re-reads its base position
  after a relayout; the static-blur cache invalidates on parameter change;
  the settings dialog is released between opens; `on_shadow_toggle` covers the
  debug panel.
- Suite total: 35 → **48 cases**, all passing; `compileall` clean; offscreen
  startup with plugin restore exits 0.

### Added in the R8 pass
- `tests/test_regressions_core.py` — the OSC probe holds its serialization
  lock while listening and releases it afterwards; an unusable UDP 9001 is
  indeterminate, not “disabled”; `send_message()` reports failure when
  composition raises; every `get_icon()` name resolves to a parseable SVG.
- Suite total: 48 → **55 cases**, all passing.

## Rename pass — final product name `VRCOSC Pulse`

The repository's final name is `Vrcosc-Pulse`, so the product was renamed to
**VRCOSC Pulse** throughout, and the legacy `vrc_qt` naming was removed rather
than left as a compatibility layer.

1. **Branding** — window title, header label, tray tooltip and balloon, settings
   copy, `app/ui/design.py` docstring, and the PyInstaller `name` are all
   `VRCOSC Pulse`. Historical round reports keep their dated narrative; only the
   product name they refer to changed (a literal `ChatBox Pulse(1).zip` upload
   reference was preserved verbatim).
2. **Packaging** — `VRC_QT.spec` → `VRCOSC_Pulse.spec`; every documentation
   reference to the old filename updated. The spec never listed the legacy
   `vrc_qt` import spellings, contrary to what the old `CLAUDE.md` claimed.
3. **Legacy imports removed** — all six `try: from vrc_qt… except
   ModuleNotFoundError:` fallback pairs are gone (`main.py`,
   `app/main_window.py` ×2, `app/dialogs/settings.py` ×2, `app/ui/panels.py`,
   `app/ui/background.py`). They can never succeed: no `vrc_qt` package exists.
   Package docstrings in `app/`, `utils/`, `plugins/` updated.
4. **Preferences migrated** — `.vrc_qt_prefs.json` →
   `.vrcosc_pulse_prefs.json`. `load_prefs()` reads the legacy file once when the
   new one is absent, writes it to the new path, and **leaves the legacy file in
   place** as a safety net. `_legacy_prefs_path()` deliberately resolves inside
   the same directory as `_prefs_path()` so tests that redirect the prefs path
   cannot read a real user's home directory. Atomic-write temp prefix is now
   `.vrcosc_pulse_prefs_`.
5. **Other names** — console log file `~/.vrc_qt.log` → `~/.vrcosc_pulse.log`;
   plugin entry-point group `vrc_qt.plugins` → `vrcosc_pulse.plugins`.
6. **Unused import removed** — `typing.Optional` in `main.py`.

Documentation corrected in the same pass (all were stale, not rename artefacts):
`CLAUDE.md` no longer claims `HAS_VRCHATMSG` is hardcoded `False` (it is set per
import branch), no longer documents the removed `app/ui_components.py`
(`AnimatedCardOverlay`), no longer says the repo has no test suite, and records
the new preferences filename.

### Added in the rename pass
- `tests/test_state.py` — legacy→new prefs migration writes the new file and
  returns the legacy payload; the new file wins when both exist; the legacy
  lookup stays in the prefs directory; the filenames are pinned to the final
  names. Tests now reference `state.PREFS_FILENAME` / `state.TMP_PREFIX` instead
  of hardcoding filenames.
- Suite total: 55 → **59 cases**, all passing; `compileall` clean; offscreen
  startup with plugin restore exits 0.

## Bug-hunt pass (R9) — 12 defects, all reproduced before fixing

Static analysis (`pyflakes`, plus a scripted sweep of the real user flows) and
three parallel deep reads of the UI layer. Every defect below was reproduced with
a script **before** the fix and re-run **after** it. Nothing is reported from
static reasoning alone; two candidates that failed to reproduce were dropped.

Severity order as reported by the reviewers.

1. **Cross-thread send toggle either deadlocks or crashes** (`app/mixins/sending.py:39`)
   — the guard used the two-arg `QTimer.singleShot(0, self._on_toggle_send_main)`.
   That overload creates the timer in the *calling* thread, so it never dispatches
   back to the GUI thread: from a plain `threading.Thread` the slot never runs and
   `_toggle_pending` stays `True` forever, silently dropping every later
   cross-thread request; from a `QThread` with an event loop the slot runs *in the
   worker* and touches widgets, giving `access violation` (reproduced stack:
   `update_osc_preview` → `setPlainText`). Now uses the context overload
   `QTimer.singleShot(0, self, self._on_toggle_send_main)`. Verified: repeated
   cross-thread toggles now start/stop correctly on the GUI thread.
2. **Blur strength decayed to nothing and never recovered** (`app/ui/panels.py:338`)
   — `update_background()` used `int(self.blur_strength)` as the animation target,
   but that attribute is what the running animation writes every frame. A wallpaper
   change mid-transition therefore adopted the *intermediate* value as the new
   target: 24→14→9→6→4→2→1. Since `_deferred_resize()` re-applies the wallpaper on
   every window resize, dragging the window killed the acrylic blur permanently.
   Now a dedicated `_blur_target` holds the user's intent.
3. **Explicit blur settings were overwritten by the running transition**
   (`app/ui/panels.py:190`) — `set_params(blur_strength=…)` assigned the value but
   never stopped `_blur_anim`, whose next ticks kept writing and finally parked the
   property on the *old* `endValue`. Setting 40 ended up at 24 (measured); in the
   real app, turning off performance mode or moving the blur slider within 300 ms
   of a wallpaper change did nothing. `set_params` now stops the animation and
   updates `_blur_target`.
4. **Transition composite was always ~60 % opaque** (`app/ui/background.py:186`)
   — the old image was drawn at `(1-t)` and the new at `t`. Because
   `QPainter` composites sequentially, the result is `old*(1-t)² + new*t`, not a
   linear crossfade, so the missing opacity exposed the window base colour for the
   whole 300 ms. Measured: a pure-white wallpaper on a black base rendered
   `rgb(118,118,118)` mid-transition. Now the old image is laid down opaque and the
   new one is drawn at `t`, giving `new*t + old*(1-t)` — measured white at every
   `t`. (A first attempt that only fixed the clear/blur ratio split was insufficient
   and was corrected after measurement.)
5. **Resize left large unpainted holes** (`app/ui/panels.py:473`) — `paintEvent`
   drew `_final_pixmap` at `(0, 0)` without scaling. Repaints are deferred through
   a frame limiter, so a paint usually arrives with a pixmap from the *previous*
   size. Measured after 400×300 → 700×500: the region outside the stale pixmap had
   `alpha=0`. Now drawn with `drawPixmap(rect, pixmap, pixmap.rect())`.
6. **Performance mode re-enabled a shadow the user had switched off**
   (`app/mixins/theme.py:588`) — it called `on_shadow_toggle(not enabled,
   record=False)` unconditionally. `record=False` protects the *preference* field
   but still forces the visual state, and `MainWindow.__init__` calls this on every
   startup, so `shadow_enabled=False` on disk rendered with shadows on. Now gated on
   `_shadow_enabled`; both directions verified.
7. **Luminance refresh wiped the pink group-title bars**
   (`app/mixins/wallpaper.py:218`) — `setStyleSheet` replaces wholesale, and this
   method runs on every frame of the 300 ms luminance interpolation, so
   `QWidget#toolGroupTitle { background-color; border-radius }` was destroyed and
   the「常规 / 性能」bars became bare text (measured `#efefef` instead of
   `#fff0f4`). Those titles are brand-coloured and owned by `apply_theme()`, so they
   are no longer touched here. The countdown label still tracks the secondary grey,
   but now writes the full rule so its `font-size: 10px` survives.
8. **Long input silently dropped every addition, or split one in half**
   (`app/core/composer.py:111`) — the final clip was a hard slice, so a 135-char
   message plus CPU/RAM produced `"...\n[CPU: 42"` — an unclosed bracket sent to the
   chatbox (and a 144-char message dropped all additions). `fit_within_limit()` now
   keeps the raw text and appends only additions that fit whole.
9. **Button press animation never ran** (`app/mixins/theme.py:536`) — the classic
   PySide6 trap: the second argument of `QPropertyAnimation(target, b"geometry")` is
   the *property name*, so with no parent the local `anim` was garbage-collected
   before it could tick (measured: geometry unchanged on press). A parent is now
   passed. This exposed a second, previously masked bug: `_btn_geo` was captured
   before the first layout pass (`QRect(0,0,640,480)` while the button actually sat
   at `(18,318,252,54)`), so merely fixing the reference would have teleported the
   button to the top-left. The base geometry is now re-read on press.
10. **Heart-rate failures rendered as healthy** (`app/mixins/debug.py:171`) — any
    non-`None`-missing BPM got `SUCCESS` green plus the breathing dot, so
    「连接失败」, 「订阅失败」and 「bleak 不可用」all looked like a working monitor.
    Status is now classified: failure/unavailable → warning colour, no breathing;
    connected-but-no-data → green with breathing.
11. **Leaving performance mode discarded the user's blur setting**
    (`app/mixins/theme.py:598`) — it restored a hard-coded `6` while the slider and
    prefs said 14. Now restores `_current_blur_strength`.
12. **`app/hr.py` used a deprecated asyncio entry point** (`app/hr.py:355`) —
    `asyncio.get_event_loop()` in the standalone debug block emits
    `DeprecationWarning: There is no current event loop` and becomes a
    `RuntimeError` on Python 3.14. The block only throttles a print, so it uses
    `time.sleep()`.

### Not defects (investigated and dropped)
- `utils/blur.py` caches by `QPixmap.cacheKey()`, which Qt may reuse — the
  collision could not be reproduced (keys were monotonic across reuse attempts).
- `@safe_metric("temps", default={})` shares one mutable default dict, but the
  producer succeeded in every reachable path and no caller mutates the result.
- `app/ui/animation.py` — the queue's `_running` flag, `submit()` trimming and
  `_done()` re-entry were each verified and hold.
- `MainWindow.hr_dot_anim` raises `RuntimeError` only when touched **after**
  `app.exec()` returns; probed from inside the running event loop it is alive and
  the breathing state machine works.

### Added in the R9 pass
- `tests/test_composer.py` — truncation never splits an addition across the whole
  120–160 character range, a full-length raw message drops additions entirely, and
  additions that do fit are kept whole.
- `tests/test_regressions_ui.py` — cross-thread `on_toggle_send()` is dispatched to
  the GUI thread and resets `_toggle_pending`; repeated wallpaper changes no longer
  decay the blur target; `set_params` overrides a running transition; the
  performance-mode/shadow preference round-trips in both directions; group-title and
  countdown stylesheets survive luminance updates; the button press animation
  actually shrinks the button without jumping to `(0,0)`; heart-rate failure
  statuses are not success-green; the transition composite stays opaque and blends
  both wallpapers; blur is restored after leaving performance mode.
- Suite total: 59 → **76 cases**, all passing; `compileall` clean; offscreen startup
  with plugin restore exits 0.

## Bug-hunt pass (R9, continued) — appearance/settings cluster

The third reviewer (settings dialog, layout, UI components) never returned and was
stopped; those files were then reviewed directly. Three more defects, same rule:
reproduced first, re-run after the fix.

13. **Appearance sliders never reflected the real values** (`app/dialogs/settings.py:769`)
    — the blur / white-alpha / corner-radius sliders were hard-coded to
    `setValue(14/28/16)` and never read `_current_blur_strength` /
    `_current_white_alpha` / `_current_corner_radius`. Measured: the user sets
    `20 / 45 / 24`, reopens the dialog, and sees `14 / 28 / 16`. Now seeded from the
    live values. The ordering constraint that keeps this safe — `setValue` must stay
    *before* `valueChanged.connect`, otherwise building the dialog would immediately
    call `on_strength_change` and overwrite the user's settings — is preserved and
    asserted by a test.
14. **Startup ignored the saved blur strength** (`app/mixins/wallpaper.py:371`) —
    `_apply_initial_wallpaper()` applied the per-panel `_default_blurs`
    (24/18/12/6) *after* `set_performance_mode()`, so it clobbered the user value the
    latter had just restored. Measured with `performance_mode=False,
    blur_strength=20`: panels rendered at `[24, 18, 12, 6]` while the dialog said 20.
    `on_strength_change`, `set_performance_mode` and `toggle_acrylic` all use one
    uniform `_current_blur_strength`, so startup was the odd one out; it now matches,
    and the dead `_default_blurs` dict was removed.
    **Visible behaviour change:** panels no longer differ in blur (24/18/12/6); all
    four follow the single 「模糊强度」 slider (default 14).
15. **High-blur hint never cleared** (`app/dialogs/settings.py:604`) —
    `update_high_blur_hint()` only had a `strength >= 20` branch. Measured: raise
    blur to 25 → hint appears; lower it to 5 → the hint is still on screen, now
    claiming something untrue. Added the missing `else: clear()`.

### Also fixed in this pass (test hygiene, not a product defect)
`MainWindowRegressionTests._new_window()` cleaned up with `window.close()` only,
which fires `closeEvent` but leaves the Qt object alive. After ten new cases were
added to that class, the accumulated windows (each with its own timers and
animations) slowed the event loop enough that the pre-existing
`ToggleSwitchSyncTests` assertion — which waits `QTest.qWait(260)` for a 160 ms
knob animation — read `knobPos == 0.0` and failed. The failure appeared **only**
when the whole class ran: each new case paired individually with that test passed,
so it is a cumulative-load effect, not a logic error. Cleanup now does
`close() + deleteLater() + processEvents()`; the full suite passes twice in a row.

### Added in this pass
- `tests/test_regressions_ui.py` — appearance sliders report the live values and
  building the dialog does not overwrite them; startup honours the saved blur
  strength for all four panels; the high-blur hint clears when the blur is lowered.
- Suite total: 76 → **79 cases**, all passing (run twice for determinism).


