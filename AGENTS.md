# Repository Guidelines

## Project Structure & Module Organization

`main.py` is the application entry point. Most code lives under `app/`: `core/` contains OSC, message composition, state, and system metrics; `ui/` contains layouts, widgets, styles, and background effects; `dialogs/` contains settings UI; and `main_window.py` coordinates the application. Plugins live in `plugins/`, with bundled implementations in `plugins/local/`. Utility code belongs in `utils/`, and runtime assets belong in `resources/fonts/` or `resources/icons/`.

Treat `build/`, `dist23/`, `dist24/`, `__pycache__/`, `.pyc` files, and packaged executables as generated artifacts. Do not edit them directly. Tests live under `tests/` mirroring source layout (stdlib `unittest`; `python -m unittest discover -s tests -t .`).

## Build, Test, and Development Commands

- `python main.py`: run the application locally.
- `$env:QT_QPA_PLATFORM='offscreen'; python main.py`: start Qt without a display for smoke diagnostics on Windows.
- `python -m compileall -q main.py app plugins utils`: check all Python sources for syntax errors.
- `python -m unittest discover -s tests -t .`: run the unit test suite (stdlib; no pytest required).
- `pyinstaller VRCOSC_Pulse.spec`: build the packaged Windows executable (`VRCOSC Pulse`). Review `VRCOSC_Pulse.spec` paths and generated output before publishing.

Required packages: `PySide6`, `python-osc`. Optional hardware integrations are listed in `requirements.txt`.

## Coding Style & Naming Conventions

Use Python 3 type hints, four-space indentation, UTF-8 source files, and PEP 8 naming: `snake_case` for functions and modules, `PascalCase` for classes, and `UPPER_CASE` for constants. Keep platform-specific and optional imports guarded with narrow exception handling. Log actionable failures; avoid silent `except Exception: pass` in core behavior. Keep Qt widget updates on the main thread.

## Testing Guidelines

Use stdlib `unittest` (pytest optional). Name files `test_<module>.py` and tests `test_<behavior>()`. Prioritize pure logic in `app/core/`, plugin dependency ordering, preference persistence, and OSC failure paths. Use fakes for UDP, BLE, system APIs, and Qt side effects; tests must not require VRChat or physical hardware.

## Commit & Pull Request Guidelines

No Git history is present, so no existing convention can be inferred. Use short imperative commits, optionally with a scope, for example `fix(osc): handle failed sends`. Pull requests should explain behavior changes, list verification commands, link relevant issues, and include screenshots for visible UI changes. Do not commit local preferences, caches, or rebuilt binaries unless the release process explicitly requires them.
