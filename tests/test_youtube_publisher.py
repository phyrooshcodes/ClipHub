"""Unit tests for YouTube auto-publisher components."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from datetime import datetime, time as dtime
from pathlib import Path

TEST_STATE = Path(tempfile.gettempdir()) / "obscura-youtube-publisher-tests"
os.environ["XDG_STATE_HOME"] = str(TEST_STATE)

from modules.publishers.youtube.scheduler import calculate_schedule_target
from modules.publishers.youtube.publisher import (
    validate_youtube_video,
    is_youtube_connected,
    disconnect_youtube,
    YouTubeUploadResult,
)


class YouTubePublisherTests(unittest.TestCase):
    def setUp(self) -> None:
        shutil.rmtree(TEST_STATE, ignore_errors=True)
        self.video = Path(tempfile.gettempdir()) / "test_yt_video.mp4"
        self.video.write_bytes(b"mock video bytes for testing")

    def tearDown(self) -> None:
        self.video.unlink(missing_ok=True)
        shutil.rmtree(TEST_STATE, ignore_errors=True)

    def test_schedule_target_calculation_after_midnight(self) -> None:
        # Given current time is 09:30 AM on July 20, 2026
        dt = datetime(2026, 7, 20, 9, 30, 0)
        target_dt, date_str, time_str = calculate_schedule_target(now=dt)
        
        # Today's 12:00 AM (00:00) has passed -> Target must be July 21, 2026 at 12:00 AM
        self.assertEqual(target_dt.date().day, 21)
        self.assertEqual(target_dt.date().month, 7)
        self.assertEqual(target_dt.date().year, 2026)
        self.assertEqual(time_str, "12:00 AM")
        self.assertEqual(date_str, "Jul 21, 2026")

    def test_schedule_target_calculation_at_exact_midnight(self) -> None:
        # Given current time is exactly 00:00 AM (start of day)
        dt = datetime(2026, 7, 20, 0, 0, 0)
        target_dt, date_str, time_str = calculate_schedule_target(now=dt)
        
        # Today's 12:00 AM has not passed -> Target is July 20, 2026 at 12:00 AM
        self.assertEqual(target_dt.date().day, 20)
        self.assertEqual(time_str, "12:00 AM")

    def test_validate_youtube_video_rejects_missing_file(self) -> None:
        with self.assertRaises(FileNotFoundError):
            validate_youtube_video("/path/does/not/exist.mp4")

    def test_validate_youtube_video_rejects_invalid_extension(self) -> None:
        txt_file = Path(tempfile.gettempdir()) / "invalid.txt"
        txt_file.write_text("hello")
        try:
            with self.assertRaises(ValueError):
                validate_youtube_video(str(txt_file))
        finally:
            txt_file.unlink(missing_ok=True)

    def test_youtube_connected_and_disconnect(self) -> None:
        profile = TEST_STATE / "obscura-clips" / "youtube" / "browser-profile"
        profile.mkdir(parents=True, exist_ok=True)
        (profile / "state.dat").write_text("session")
        
        self.assertTrue(is_youtube_connected())
        disconnect_youtube()
        self.assertFalse(is_youtube_connected())


if __name__ == "__main__":
    unittest.main()
