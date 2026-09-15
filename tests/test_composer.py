import sys
import unittest
from pathlib import Path
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.core.composer import compose_full_message


class ComposeFullMessageTests(unittest.TestCase):
    def test_empty_raw_returns_none(self):
        self.assertIsNone(compose_full_message(""))
        self.assertIsNone(compose_full_message("   "))

    def test_raw_only_when_all_includes_off(self):
        out = compose_full_message(
            "hello",
            wrap_newlines=False,
            include_time=False,
            include_window_title=False,
            include_music=False,
            include_idle=False,
            include_cpu=False,
            include_ram=False,
            include_gpu=False,
            include_temp=False,
            include_hr=False,
        )
        self.assertEqual(out, "hello")

    def test_max_len_truncates(self):
        out = compose_full_message(
            "x" * 200,
            wrap_newlines=False,
            include_time=False,
            include_window_title=False,
            include_music=False,
            include_idle=False,
            include_cpu=False,
            include_ram=False,
            include_gpu=False,
            include_temp=False,
            include_hr=False,
            max_len=10,
        )
        self.assertEqual(out, "x" * 10)

    @patch("app.core.composer.get_idle_seconds", return_value=120)
    @patch("app.core.composer.get_active_window_title", return_value=None)
    @patch("app.core.composer.get_smtc_info", return_value=None)
    @patch("app.core.composer.get_cpu_usage", return_value=None)
    @patch("app.core.composer.get_ram_usage", return_value=None)
    @patch("app.core.composer.get_current_hr", return_value=None)
    def test_idle_addition_when_above_threshold(self, *_mocks):
        out = compose_full_message(
            "hi",
            wrap_newlines=False,
            include_time=False,
            include_window_title=True,
            include_music=True,
            include_idle=True,
            idle_threshold=60,
            include_cpu=True,
            include_ram=True,
            include_gpu=False,
            include_temp=False,
            include_hr=True,
        )
        self.assertIsNotNone(out)
        self.assertIn("[已挂机:", out)
        self.assertTrue(out.startswith("hi"))

    @patch("app.core.composer.get_idle_seconds", return_value=10)
    @patch("app.core.composer.get_active_window_title", return_value="Notepad")
    @patch("app.core.composer.get_smtc_info", return_value="♪ Artist - Song")
    @patch("app.core.composer.get_cpu_usage", return_value=12.0)
    @patch("app.core.composer.get_ram_usage", return_value=34.0)
    @patch("app.core.composer.get_current_hr", return_value=72)
    def test_full_additions_with_wrap(self, *_mocks):
        out = compose_full_message(
            "status",
            wrap_newlines=True,
            include_time=False,
            include_window_title=True,
            include_music=True,
            include_idle=True,
            idle_threshold=60,
            include_cpu=True,
            include_ram=True,
            include_gpu=False,
            include_temp=False,
            include_hr=True,
        )
        self.assertIsNotNone(out)
        self.assertIn("Notepad", out)
        self.assertIn("♪ Artist - Song", out)
        self.assertIn("CPU: 12%", out)
        self.assertIn("RAM: 34%", out)
        self.assertIn("[HR: 72bpm]", out)
        self.assertNotIn("[已挂机:", out)
        self.assertIn("\n", out)


if __name__ == "__main__":
    unittest.main()
