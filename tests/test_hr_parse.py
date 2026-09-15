import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.hr import parse_heart_rate_measurement


class ParseHeartRateTests(unittest.TestCase):
    def test_uint8(self):
        # flag 0x00 → uint8, bpm 72
        self.assertEqual(parse_heart_rate_measurement(bytes([0x00, 72])), 72)

    def test_uint16(self):
        # flag 0x01 → uint16 LE, bpm 300
        self.assertEqual(parse_heart_rate_measurement(bytes([0x01, 0x2C, 0x01])), 300)

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            parse_heart_rate_measurement(b"")

    def test_short_uint8_raises(self):
        with self.assertRaises(ValueError):
            parse_heart_rate_measurement(bytes([0x00]))

    def test_short_uint16_raises(self):
        with self.assertRaises(ValueError):
            parse_heart_rate_measurement(bytes([0x01, 0x2C]))


if __name__ == "__main__":
    unittest.main()
