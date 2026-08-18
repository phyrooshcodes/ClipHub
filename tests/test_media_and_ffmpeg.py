import os
import sys
import unittest
import numpy as np
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.renderer import escape_ffmpeg_filter_path, check_nvenc_available
from modules.face_tracker import OneEuroFilter
from modules.audio_demux import get_video_duration


class TestMediaAndFFmpeg(unittest.TestCase):
    def test_escape_ffmpeg_filter_path(self):
        # Empty string handling
        self.assertEqual(escape_ffmpeg_filter_path(""), "")
        self.assertEqual(escape_ffmpeg_filter_path(None), "")

        # Path with single quote
        test_path = "temp/clip's_subtitles.ass"
        escaped = escape_ffmpeg_filter_path(test_path)
        self.assertIn(r"'\''", escaped)
        self.assertFalse(escaped.endswith("\\"))

    def test_one_euro_filter(self):
        filt = OneEuroFilter(freq=30.0, min_cutoff=0.2, beta=0.005)
        
        # First frame should return exactly the input
        val0 = filt.filter(100.0)
        self.assertEqual(val0, 100.0)

        # Subsequent frames should smoothly follow without exploding or NaN
        for pos in [102.0, 105.0, 110.0, 120.0, 125.0]:
            smooth_pos = filt.filter(pos)
            self.assertTrue(np.isfinite(smooth_pos))
            self.assertTrue(100.0 <= smooth_pos <= 130.0)

    def test_get_video_duration_nonexistent(self):
        # Graceful zero duration for missing files without throwing
        dur = get_video_duration("nonexistent_video_file_xyz.mp4")
        self.assertEqual(dur, 0.0)


if __name__ == "__main__":
    unittest.main()
