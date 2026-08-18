import os
import sys
import unittest
import threading
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.hook_detector import _parse_json_response, _validate_and_clamp_clips
from modules.subtitle_engine import generate_ass_subtitles, _sanitize_word
from api.jobs import JobRegistry
from api.pipeline import _list_clips


class TestAdversarialPipeline(unittest.TestCase):
    def test_adversarial_json_parsing(self):
        # Text with markdown and text before/after JSON
        tricky_payload = """
        Here are the viral clips you requested:
        ```json
        [
          {
            "clip_title": "Fix Your Sleep Tonight",
            "start_time": "01:00",
            "end_time": "01:45",
            "viral_score": 9.8,
            "hook_explanation": "Direct actionable advice"
          }
        ]
        ```
        Hope this helps! Let me know if you need more.
        """
        parsed = _parse_json_response(tricky_payload)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["clip_title"], "Fix Your Sleep Tonight")

        # Object-wrapped with 'moments' key
        moments_payload = """
        {"status": "success", "moments": [{"clip_title": "Dopamine Protocol", "start_time": "02:00", "end_time": "02:50"}]}
        """
        parsed_moments = _parse_json_response(moments_payload)
        self.assertEqual(len(parsed_moments), 1)
        self.assertEqual(parsed_moments[0]["clip_title"], "Dopamine Protocol")

        # Complete garbage -> must raise ValueError
        with self.assertRaises(ValueError):
            _parse_json_response("No JSON anywhere in this text at all!")

    def test_concurrent_job_registry_claims(self):
        reg = JobRegistry()
        job_id = f"concurrent_stress_job_{os.getpid()}"
        reg.register(job_id, "video.mp4", "video.mp4")

        results = []
        threads = []

        def claim_worker():
            success = reg.claim_execution(job_id)
            results.append(success)

        # Launch 20 concurrent threads attempting to claim execution simultaneously
        for _ in range(20):
            t = threading.Thread(target=claim_worker)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Exactly 1 thread must succeed in claiming the job
        self.assertEqual(results.count(True), 1)
        self.assertEqual(results.count(False), 19)

    def test_adversarial_path_traversal_in_list_clips(self):
        # Attempting directory traversal in job_id parameter
        evil_job_ids = [
            "../../",
            "..\\..\\",
            "/etc/passwd",
            "C:\\Windows\\System32",
            "job_123/../../secret",
            "job_123\x00_hidden"
        ]
        for evil_id in evil_job_ids:
            clips = _list_clips(job_id=evil_id)
            self.assertEqual(clips, [])

    def test_clean_text_for_ass_escaping(self):
        raw_text = "Watch{an5}\\N"
        cleaned = _sanitize_word(raw_text)
        self.assertNotIn("{", cleaned)
        self.assertNotIn("}", cleaned)
        self.assertNotIn("\\", cleaned)

    def test_subtitle_generation_with_empty_and_extreme_inputs(self):
        temp_ass = "temp/test_adversarial.ass"
        os.makedirs("temp", exist_ok=True)
        try:
            # Empty words list
            res_empty = generate_ass_subtitles([], 0.0, 10.0, temp_ass)
            self.assertTrue(os.path.exists(res_empty))
            
            # Words with unicode, emoji, special symbols
            special_words = [
                {"word": "Hello🔥", "start": 1.0, "end": 1.5},
                {"word": "world—special", "start": 1.6, "end": 2.0},
                {"word": "accent: café", "start": 2.1, "end": 2.5}
            ]
            res_special = generate_ass_subtitles(special_words, 1.0, 3.0, temp_ass)
            self.assertTrue(os.path.exists(res_special))
        finally:
            if os.path.exists(temp_ass):
                try: os.remove(temp_ass)
                except Exception: pass


if __name__ == "__main__":
    unittest.main()
