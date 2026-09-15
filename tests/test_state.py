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

from app.core import state


class PrefsTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._path = os.path.join(self._tmpdir.name, state.PREFS_FILENAME)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_load_missing_returns_empty(self):
        with patch.object(state, "_prefs_path", return_value=self._path):
            self.assertEqual(state.load_prefs(), {})

    def test_save_then_load(self):
        payload = {"auto_hr": True, "spin_interval": 45, "nested": {"a": 1}}
        with patch.object(state, "_prefs_path", return_value=self._path):
            state.save_prefs(payload)
            self.assertEqual(state.load_prefs(), payload)

    def test_save_is_atomic_no_tmp_left(self):
        with patch.object(state, "_prefs_path", return_value=self._path):
            state.save_prefs({"k": "v"})
        leftovers = [
            f for f in os.listdir(self._tmpdir.name)
            if f.startswith(state.TMP_PREFIX) and f.endswith(".tmp")
        ]
        self.assertEqual(leftovers, [])
        with open(self._path, encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"k": "v"})

    def test_load_corrupt_returns_empty(self):
        Path(self._path).write_text("{not json", encoding="utf-8")
        with patch.object(state, "_prefs_path", return_value=self._path):
            self.assertEqual(state.load_prefs(), {})

    # --- 命名迁移（vrc_qt / ChatBox Pulse → VRCOSC Pulse）---

    def test_legacy_prefs_are_migrated_to_new_filename(self):
        """旧文件存在、新文件缺失时：内容被返回，并落盘到新文件名。"""
        legacy_path = os.path.join(self._tmpdir.name, state.LEGACY_PREFS_FILENAME)
        payload = {"spin_interval": 60, "auto_hr": True}
        Path(legacy_path).write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
        with patch.object(state, "_prefs_path", return_value=self._path):
            self.assertEqual(state.load_prefs(), payload)
        # 已迁移到新路径
        self.assertTrue(os.path.exists(self._path))
        with open(self._path, encoding="utf-8") as f:
            self.assertEqual(json.load(f), payload)

    def test_new_prefs_win_over_legacy(self):
        """新文件已存在时，不再读取旧文件。"""
        legacy_path = os.path.join(self._tmpdir.name, state.LEGACY_PREFS_FILENAME)
        Path(legacy_path).write_text(json.dumps({"from": "legacy"}), encoding="utf-8")
        Path(self._path).write_text(json.dumps({"from": "current"}), encoding="utf-8")
        with patch.object(state, "_prefs_path", return_value=self._path):
            self.assertEqual(state.load_prefs(), {"from": "current"})

    def test_legacy_lookup_stays_in_same_directory(self):
        """_legacy_prefs_path 必须与新路径同目录，避免读到真实主目录的旧配置。"""
        with patch.object(state, "_prefs_path", return_value=self._path):
            self.assertEqual(
                state._legacy_prefs_path(),
                os.path.join(self._tmpdir.name, state.LEGACY_PREFS_FILENAME),
            )

    def test_prefs_filename_is_the_final_name(self):
        self.assertEqual(state.PREFS_FILENAME, ".vrcosc_pulse_prefs.json")
        self.assertEqual(state.LEGACY_PREFS_FILENAME, ".vrc_qt_prefs.json")


if __name__ == "__main__":
    unittest.main()
