"""Simple preferences persistence utilities.

Persist lightweight user preferences to a JSON file under the user home.
Stores wallpaper + general settings for VRCOSC Pulse.

命名迁移：偏好文件从旧名 ``.vrc_qt_prefs.json`` 改为
``.vrcosc_pulse_prefs.json``。``load_prefs()`` 会在新文件不存在时读取旧文件并
自动迁移，因此升级不会丢失用户已有设置。
"""

from typing import Dict, Any, Optional
import os
import sys
import json
import tempfile
import logging


logger = logging.getLogger(__name__)


PREFS_FILENAME = ".vrcosc_pulse_prefs.json"
# 旧版（vrc_qt / ChatBox Pulse 时期）的偏好文件名，仅用于一次性迁移读取
LEGACY_PREFS_FILENAME = ".vrc_qt_prefs.json"
# 原子写入的临时文件前缀
TMP_PREFIX = ".vrcosc_pulse_prefs_"


def _resolve_path(fname: str) -> str:
    """Return a robust per-user path for ``fname``.

    Priority:
    1) User home via expanduser
    2) Platform-specific user data/config dirs
       - Windows: LOCALAPPDATA / APPDATA / USERPROFILE
       - macOS: ~/Library/Application Support
       - Linux/Unix: $XDG_CONFIG_HOME or HOME
    3) OS temp directory
    """
    # 1) Home via expanduser
    try:
        home = os.path.expanduser("~")
        if isinstance(home, str) and home:
            return os.path.join(home, fname)
    except Exception:
        pass
    # 2) Platform-specific dirs
    try:
        if sys.platform.startswith('win'):
            base = os.environ.get('LOCALAPPDATA') or os.environ.get('APPDATA') or os.environ.get('USERPROFILE')
            if base:
                return os.path.join(base, fname)
        elif sys.platform == 'darwin':
            base = os.path.expanduser('~/Library/Application Support')
            if base:
                return os.path.join(base, fname)
        else:
            base = os.environ.get('XDG_CONFIG_HOME') or os.environ.get('HOME')
            if base:
                return os.path.join(base, fname)
    except Exception:
        pass
    # 3) Temp directory as last resort
    try:
        return os.path.join(tempfile.gettempdir(), fname)
    except Exception:
        # Absolute last fallback: relative file next to process cwd
        return fname


def _prefs_path() -> str:
    """当前版本的偏好文件路径（测试会 patch 此函数以重定向）。"""
    return _resolve_path(PREFS_FILENAME)


def _legacy_prefs_path() -> str:
    """旧版偏好文件路径。

    刻意与新文件放在同一目录：这样测试把 ``_prefs_path`` 重定向到临时目录后，
    旧文件查找也局限在临时目录内，不会误读用户真实主目录里的配置。
    """
    current = _prefs_path()
    return os.path.join(os.path.dirname(current), LEGACY_PREFS_FILENAME)


def _read_prefs_file(path: str) -> Optional[Dict[str, Any]]:
    """读取并解析偏好文件；不存在或损坏时返回 None。"""
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
    except Exception as e:
        logger.warning("Failed to load prefs from %s: %s", path, e)
    return None


def load_prefs() -> Dict[str, Any]:
    """读取偏好；新文件不存在时自动从旧版文件名迁移一次。"""
    path = _prefs_path()
    data = _read_prefs_file(path)
    if data is not None:
        return data

    legacy = _read_prefs_file(_legacy_prefs_path())
    if legacy:
        logger.info(
            "Migrating preferences from legacy %s to %s",
            LEGACY_PREFS_FILENAME, PREFS_FILENAME,
        )
        # 迁移失败也不影响本次返回：旧配置仍然可用（只是下次会再迁移一遍）
        save_prefs(legacy)
        return legacy
    return {}


def save_prefs(prefs: Dict[str, Any]) -> None:
    path = _prefs_path()
    try:
        # Ensure target directory exists (in case env points to a custom dir)
        d = os.path.dirname(path)
        if d and not os.path.exists(d):
            try:
                os.makedirs(d, exist_ok=True)
            except Exception:
                pass
        # Atomic write: temp file in same dir, then replace
        target_dir = d if d else os.getcwd()
        fd, tmp_path = tempfile.mkstemp(
            dir=target_dir, prefix=TMP_PREFIX, suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(prefs, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception as e:
        logger.warning("Failed to save prefs to %s: %s", path, e)
