"""Offline tests for the personal Instagram queue; no browser or account required."""

from __future__ import annotations

import os
import shutil
import tempfile
import time
import unittest
import uuid
from pathlib import Path


TEST_STATE = Path(tempfile.gettempdir()) / "cliphub-instagram-queue-tests"
os.environ["XDG_STATE_HOME"] = str(TEST_STATE)

from modules import instagram_queue  # noqa: E402
from modules.publisher_ig import InstagramUploadError, InstagramUploadResult  # noqa: E402


class InstagramQueueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        shutil.rmtree(TEST_STATE, ignore_errors=True)
        cls.original_validate = instagram_queue.validate_reel_video
        cls.original_upload = instagram_queue.post_instagram_reel
        instagram_queue.validate_reel_video = lambda _path: 10.0
        instagram_queue.post_instagram_reel = cls._successful_upload
        cls.queue = instagram_queue.InstagramQueue()
        cls.queue.set_cooldown(0)

    def setUp(self) -> None:
        self.queue.set_paused(False)
        self.video = Path(tempfile.gettempdir()) / f"cliphub-instagram-queue-{uuid.uuid4()}.mp4"
        self.video.write_bytes(f"test-video-{uuid.uuid4()}".encode())

    def tearDown(self) -> None:
        self.video.unlink(missing_ok=True)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.queue.stop()
        instagram_queue.validate_reel_video = cls.original_validate
        instagram_queue.post_instagram_reel = cls.original_upload
        shutil.rmtree(TEST_STATE, ignore_errors=True)

    @staticmethod
    def _successful_upload(_path: str, _caption: str, progress) -> InstagramUploadResult:
        progress(50, "Mock browser upload")
        return InstagramUploadResult("completed", "https://instagram.com/reel/test")

    def test_queue_completes_and_records_history(self) -> None:
        item = self.queue.enqueue(str(self.video), "Caption #test")
        for _ in range(40):
            current = self.queue.get(item["id"])
            if current and current["status"] == "completed":
                break
            time.sleep(0.1)
        self.assertEqual(current["status"], "completed")
        self.assertEqual(current["progress"], 100)
        self.assertEqual(current["reel_url"], "https://instagram.com/reel/test")
        self.assertEqual(self.queue.history()[0]["id"], item["id"])

    def test_duplicate_requires_explicit_override(self) -> None:
        self.queue.enqueue(str(self.video), "Caption")
        with self.assertRaisesRegex(ValueError, "already submitted"):
            self.queue.enqueue(str(self.video), "Caption")
        override = self.queue.enqueue(str(self.video), "Caption", allow_duplicate=True)
        self.assertEqual(override["status"], "queued")
        for _ in range(40):
            current = self.queue.get(override["id"])
            if current and current["status"] == "completed":
                break
            time.sleep(0.05)
        self.assertEqual(current["status"], "completed")

    def test_transient_failure_stops_after_three_total_attempts(self) -> None:
        def transient_failure(_path: str, _caption: str, progress) -> InstagramUploadResult:
            raise InstagramUploadError("temporary network interruption", retryable=True)

        original = instagram_queue.post_instagram_reel
        instagram_queue.post_instagram_reel = transient_failure
        try:
            item = self.queue.enqueue(str(self.video), "Caption")
            for _ in range(60):
                current = self.queue.get(item["id"])
                if current and current["status"] == "retrying":
                    # Do not wait for production backoff during an offline unit test.
                    self.queue._update(item["id"], next_attempt_at=0)
                    self.queue._wake.set()
                if current and current["status"] == "failed":
                    break
                time.sleep(0.05)
            self.assertEqual(current["status"], "failed")
            self.assertEqual(current["attempts"], 3)
            self.assertIn("Failed after 3 attempts", current["message"])
        finally:
            instagram_queue.post_instagram_reel = original

    def test_login_required_is_terminal_without_retry(self) -> None:
        def login_required(_path: str, _caption: str, progress) -> InstagramUploadResult:
            raise InstagramUploadError("Login required", status="login_required")

        original = instagram_queue.post_instagram_reel
        instagram_queue.post_instagram_reel = login_required
        try:
            item = self.queue.enqueue(str(self.video), "Caption")
            for _ in range(40):
                current = self.queue.get(item["id"])
                if current and current["status"] == "login_required":
                    break
                time.sleep(0.05)
            self.assertEqual(current["status"], "login_required")
            self.assertEqual(current["attempts"], 1)
        finally:
            instagram_queue.post_instagram_reel = original


if __name__ == "__main__":
    unittest.main()
