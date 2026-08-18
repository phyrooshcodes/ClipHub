import sys
import unittest
import numpy as np
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.native_accel import mean_absolute_difference, smooth_crop_x
from modules.subtitle_engine import html_color_to_ass, _get_ass_header


class TestNativeAndSubtitles(unittest.TestCase):
    def test_mean_absolute_difference(self):
        # Identical frames -> diff = 0.0
        frame_a = np.ones((100, 100), dtype=np.uint8) * 128
        frame_b = np.ones((100, 100), dtype=np.uint8) * 128
        self.assertAlmostEqual(mean_absolute_difference(frame_a, frame_b), 0.0)

        # Opposite frames (0 and 255) -> diff = 255.0
        frame_0 = np.zeros((100, 100), dtype=np.uint8)
        frame_255 = np.ones((100, 100), dtype=np.uint8) * 255
        self.assertAlmostEqual(mean_absolute_difference(frame_0, frame_255), 255.0)

        # Non-contiguous array slice test (must not panic)
        large_a = np.arange(200 * 200, dtype=np.uint8).reshape((200, 200))
        slice_a = large_a[::2, ::2]  # Non-contiguous strided view
        slice_b = np.copy(slice_a)
        self.assertAlmostEqual(mean_absolute_difference(slice_a, slice_b), 0.0)

        # Invalid shape mismatch
        with self.assertRaises(ValueError):
            mean_absolute_difference(np.zeros((10, 10)), np.zeros((10, 12)))

    def test_smooth_crop_x(self):
        # Empty positions -> center crop
        cx = smooth_crop_x([], crop_width=608, source_width=1920)
        self.assertEqual(cx, (1920 - 608) // 2)

        # Constant center position
        positions = [960.0] * 30
        cx = smooth_crop_x(positions, crop_width=608, source_width=1920, smoothing_window=10)
        expected_x = int(960.0 - 608 / 2.0)
        self.assertEqual(cx, expected_x)

        # Bounds clamping (left bound)
        cx_left = smooth_crop_x([50.0], crop_width=608, source_width=1920)
        self.assertEqual(cx_left, 0)

        # Bounds clamping (right bound)
        cx_right = smooth_crop_x([1900.0], crop_width=608, source_width=1920)
        self.assertEqual(cx_right, 1920 - 608)

    def test_html_color_to_ass(self):
        # Pure red (#FF0000 -> ASS &H000000FF&)
        self.assertEqual(html_color_to_ass("#FF0000"), "&H000000FF&")
        # Pure blue (#0000FF -> ASS &H00FF0000&)
        self.assertEqual(html_color_to_ass("#0000FF"), "&H00FF0000&")
        # Pure yellow (#FFFF00 -> ASS &H0000FFFF&)
        self.assertEqual(html_color_to_ass("#FFFF00"), "&H0000FFFF&")
        # Pure white (#FFFFFF -> ASS &H00FFFFFF&)
        self.assertEqual(html_color_to_ass("#FFFFFF"), "&H00FFFFFF&")
        # Pure black (#000000 -> ASS &H00000000&)
        self.assertEqual(html_color_to_ass("#000000"), "&H00000000&")

    def test_get_ass_header(self):
        header = _get_ass_header(
            preset_name="default",
            font_name="Montserrat",
            primary_color="#FFFF00",
            outline_color="#000000",
            font_size=40
        )
        self.assertIn("[Script Info]", header)
        self.assertIn("Montserrat", header)
        self.assertIn("&H0000FFFF&", header)  # Yellow primary color in ASS format


if __name__ == "__main__":
    unittest.main()
