# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Companion file: `AGENTS.md` documents project structure, coding style, testing guidelines, and commit conventions — read it too. This file covers the architecture that requires reading multiple files to understand.

## Project overview

A Windows-only Python/PySide6 desktop app ("VRCOSC Pulse") that periodically sends a status message to VRChat via OSC (`/chatbox/input` on `127.0.0.1:9000`). The message composes the user's typed text with optional additions (time, foreground window title, playing music via SMTC, idle duration, CPU/RAM/GPU usage, temperatures, BLE heart rate). The UI is a frameless-ish acrylic window over the desktop wallpaper with a system tray icon. All user-facing UI text and most code comments are in Chinese.

## Commands

- `python main.py` — run the app locally.
- `$env:QT_QPA_PLATFORM='offscreen'; python main.py` — instantiate the window without a display (smoke test on Windows).
- `python -m compileall -q main.py app plugins utils` — syntax-check all sources (this is the de-facto build check; there is no build system).
- `python -m unittest discover -s tests -t .` — run unit tests (stdlib unittest; pytest optional).
- `pyinstaller VRCOSC_Pulse.spec` — package the Windows executable (`VRCOSC Pulse`; `pathex` uses `SPECPATH`).

There is no dependency manifest. Required deps are PySide6 and python-osc; optional deps are imported defensively (see below).

## Architecture

### Startup flow (`main.py` → `app/main_window.py`)

`main.py` configures logging, creates `QApplication`, instantiates `MainWindow`, then builds a `PluginContext(app, main_window)` and runs `PluginManager(ctx).load_all()`, attaches the manager as `window.plugin_manager`, and enters `app.exec()`. If the plugin system fails it logs a warning and continues.

### Message pipeline

```
QTimer (spin_interval seconds) ──► MainWindow.compose_message()
                                      └─► app/core/composer.py:compose_full_message(raw, include_* flags...)
                                            ├─► app/core/system.py   (window title, SMTC music, idle, CPU/RAM/GPU, temps)
                                            └─► app/hr.py:get_current_hr()  (BLE heart rate)
                                      └─► app/core/osc.py:OSCClient.send_message() → /chatbox/input [text, visible]
```

`compose_full_message()` returns `None` for empty input, truncates to `max_len` (144), and appends bracketed addition groups. `MainWindow.send_message()` calls `compose_message()` (returns `""` when empty), sends via OSC, and appends to the history panel.

### Imports

The legacy `vrc_qt` package is gone. Every module now uses plain absolute
imports (`from app.…`, `from plugins.…`, `from utils.…`) or package-relative
imports (e.g. `plugins/local/*` uses `from plugins.base import Plugin`). The old
`try: from vrc_qt… except ModuleNotFoundError:` fallback pairs were removed
during the rename to VRCOSC Pulse — do not reintroduce them.

### UI assembly — `MainWindow` + `UILayoutManager` (`app/ui/layout.py`)

`MainWindow.__init__` does not build the body UI directly. It creates `UILayoutManager(self)` and calls `setup_body_layout()`. The manager builds the input/history/tool panels plus a debug panel (embedded inside the tool panel), and — critically — writes widget references back onto the `MainWindow` instance as attributes: `main_window.auto_wrap`, `auto_time`, `auto_window`, `auto_music`, `auto_idle`, `auto_hr`, `auto_hardware`, `auto_cpu`, `auto_ram`, `auto_gpu`, `auto_temp`, `spin_interval`, `osc_addr`, `status_label`, `countdown_label`, `debug_labels`, `hr_dot*`, `body`, `body_widget`, etc. `MainWindow` then reads these attributes in its logic (e.g. `compose_message()` checks `self.auto_wrap.isChecked()`). **Convention: new UI controls must be created in `UILayoutManager` and stored on `main_window`; don't build widgets inside `MainWindow` methods** (except header buttons, which MainWindow creates directly).

Other UI pieces: `app/ui/panels.py` (`AcrylicPanel` blur/rounded panels), `app/ui/widgets.py` (`QRippleWidget`, `BreathingScrollBar`), `app/ui/background.py` (`BackgroundManager` wallpaper fade/blur transitions), `app/dialogs/settings.py` (`SettingsDialog`, category list + stacked scroll pages).

### Plugin system (`plugins/`)

- `plugins/base.py` — `Plugin` is a `Protocol` (`name`, `version`, `description`, `author`, `homepage`, `requires: list[str]`; methods `activate(ctx)`, `deactivate()`, optional `install`/`update`/`uninstall`/`create_settings_widget`). `PluginContext` carries `app` and `main_window`.
- `plugins/manager.py` — `PluginManager.load_all()` discovers plugins two ways: entry points in the `vrcosc_pulse.plugins` group, and every module under `plugins/local/`. A local module must expose either a `plugin_entry()` factory returning a `Plugin`, or a no-arg `Plugin` class. Activation is ordered by the `requires` dependency list.
- Bundled plugins live in `plugins/local/`: `hello_plugin.py`, `hide_console.py`, `pause_on_y.py` (a good template — it toggles `MainWindow.start_sending()`/`stop_sending()`).

To add a plugin: create `plugins/local/<name>.py` exposing `plugin_entry()`; add the module to `VRCOSC_Pulse.spec` `hiddenimports` so it survives packaging.

### System metrics (`app/core/system.py`)

All metric getters follow a fallback chain and are wrapped so a missing optional dependency never raises:

1. Preferred source `vrchatmsg.core` — used when importable. `HAS_VRCHATMSG` is set `True` in the successful-import branch and `False` in the `except` branch, so the preferred backend activates whenever it is actually installed.
2. Fallbacks: `psutil` (CPU/RAM/temps), `GPUtil` then `pynvml` (GPU), `win32gui` (window title), `ctypes`/`GetLastInputInfo` (idle), `winsdk` SMTC (music), `/sys/class/hwmon` (Linux temps).

Each getter uses the `@safe_metric` decorator (records health into `_HEALTH`, returns a default on failure) and `_cached_call(key, ttl, producer)` for TTL caching (`TTL_*` constants, e.g. CPU 1s, temps 5s). `clear_system_cache()` and `health_check()` exist for diagnostics. The old `LibreHardwareMonitorLib.dll` integration was removed and the unused DLL has since been deleted from the repo root.

### Heart rate (`app/hr.py`)

`HeartRateMonitor` runs a `bleak`-based asyncio loop in a daemon thread; targets a Xiaomi Smart Band 9 with the standard Heart Rate Service/Measurement UUIDs. `ensure_monitor_started()` returns a module-level singleton and is restartable after `stop()`. `get_current_hr()` is what the composer calls. Checking 「心率状态」 calls `SendingMixin.on_toggle_hr`, which starts/stops the monitor; 「选择设备」 scans and connects a specific BLE device.

### Preferences (`app/core/state.py`)

`load_prefs()`/`save_prefs()` persist a JSON dict to `~/.vrcosc_pulse_prefs.json` (per-user path with platform fallbacks). Writes are atomic (temp file + `os.replace`). `load_prefs()` migrates the legacy `~/.vrc_qt_prefs.json` on first run when the new file is absent, so the rename to VRCOSC Pulse does not lose existing settings.

## Threading and Windows constraints

- Keep all Qt widget mutation on the main thread. Background work reports back through Qt signals (e.g. `oscProbeResult` from the OSC-probe thread) or thread-safe getters (`HeartRateMonitor.get_last_bpm()` takes a lock).
- Sending is guarded by `_send_lock` and a `_toggle_pending` flag to prevent re-entrant toggle races.
- Windows-specific APIs (`ctypes.windll`, `winreg`, `win32gui`, `winsdk`, SMTC) are used unguarded in some paths — they degrade via `safe_metric`, but the app only meaningfully runs on Windows.

## Known issues (from `findings.md`, worth not re-diagnosing)

- `tests/` holds a stdlib-`unittest` suite (`python -m unittest discover -s tests -t .`); see `findings.md` for remaining test gaps.
- Legacy `vrc_qt` naming has been fully removed: import fallbacks deleted, root `__init__.py` and `build/` artifacts gone, prefs migrated to `.vrcosc_pulse_prefs.json`.
- Plugin missing-dependency checks return install/enable hints (by design); no auto-enable.
