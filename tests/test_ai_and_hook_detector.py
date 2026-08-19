import sys
import unittest
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.hook_detector import _parse_json_response, _validate_and_clamp_clips, _deduplicate_clips, _parse_mmss_to_ms


class TestAiAndHookDetector(unittest.TestCase):
    def test_parse_mmss_to_ms(self):
        self.assertEqual(_parse_mmss_to_ms("00:10"), 10000)
        self.assertEqual(_parse_mmss_to_ms("01:30"), 90000)
        self.assertEqual(_parse_mmss_to_ms("65:10"), (65 * 60 + 10) * 1000)
        self.assertEqual(_parse_mmss_to_ms("1:05:10"), (3600 + 5 * 60 + 10) * 1000)

    def test_parse_json_response_direct_array(self):
        raw = '[{"clip_title": "Why You Zone Out", "start_time": "01:00", "end_time": "01:45", "viral_score": 9.5}]'
        parsed = _parse_json_response(raw)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["clip_title"], "Why You Zone Out")

    def test_parse_json_response_markdown_wrapped(self):
        raw = '```json\n[{"clip_title": "Fix Your Sleep", "start_time": "02:00", "end_time": "02:40", "viral_score": 9.2}]\n```'
        parsed = _parse_json_response(raw)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["clip_title"], "Fix Your Sleep")

    def test_parse_json_response_object_wrapped(self):
        raw = '{"clips": [{"clip_title": "Dopamine Reset", "start_time": "03:00", "end_time": "03:45", "viral_score": 9.0}]}'
        parsed = _parse_json_response(raw)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["clip_title"], "Dopamine Reset")

    def test_validate_and_clamp_clips_duration_filter(self):
        # Fake transcript words covering 100 seconds
        words = []
        for i in range(100):
            words.append({"word": f"word{i}.", "start": float(i), "end": float(i) + 0.8})

        raw_clips = [
            # Short clip at end of video (96s-99s) that cannot expand to 35s -> discarded
            {"clip_title": "Unexpandable Tail Clip", "start_time": "01:36", "end_time": "01:39", "viral_score": 8.0},
            # Valid 40s clip (10s-50s)
            {"clip_title": "Valid Standalone Clip", "start_time": "00:10", "end_time": "00:50", "viral_score": 9.5}
        ]

        valid = _validate_and_clamp_clips(raw_clips, video_duration_seconds=100.0, words=words)
        self.assertEqual(len(valid), 1)
        self.assertEqual(valid[0]["title"], "Valid Standalone Clip")
        self.assertTrue((valid[0]["end_ms"] - valid[0]["start_ms"]) >= 18000)

    def test_deduplicate_clips(self):
        clips = [
            {"start_ms": 10000, "end_ms": 50000, "hook_score": 9.5, "title": "Clip A"},
            {"start_ms": 12000, "end_ms": 52000, "hook_score": 8.0, "title": "Clip B (Overlap with A)"},
            {"start_ms": 60000, "end_ms": 100000, "hook_score": 9.0, "title": "Clip C (Distinct)"}
        ]
        deduped = _deduplicate_clips(clips, max_clips=5)
        self.assertEqual(len(deduped), 2)
        titles = [c["title"] for c in deduped]
        self.assertIn("Clip A", titles)
        self.assertIn("Clip C (Distinct)", titles)
        self.assertNotIn("Clip B (Overlap with A)", titles)


if __name__ == "__main__":
    unittest.main()
