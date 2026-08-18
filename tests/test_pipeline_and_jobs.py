import os
import sys
import time
import unittest
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.jobs import JobRegistry, Job
from api.pipeline import get_video_metadata


class TestPipelineAndJobs(unittest.TestCase):
    def test_job_registry_lifecycle(self):
        reg = JobRegistry()
        job_id = f"test_job_{int(time.time() * 1000)}"
        
        # 1. Register
        job = reg.register(job_id, "/path/to/test.mp4", "test.mp4")
        self.assertEqual(job.job_id, job_id)
        self.assertEqual(job.state, "created")
        self.assertFalse(job.started)
        self.assertFalse(job.done)

        # 2. Config
        reg.set_config(job_id, {"model": "small", "max_clips": 5})
        cfg = reg.get_config(job_id)
        self.assertEqual(cfg.get("model"), "small")

        # 3. Claim execution (should succeed first time)
        claimed = reg.claim_execution(job_id)
        self.assertTrue(claimed)
        
        # Claim execution second time without restart should return False
        claimed_again = reg.claim_execution(job_id)
        self.assertFalse(claimed_again)

        # 4. Events
        reg.add_event(job_id, {"type": "stage", "stage": 1, "label": "Audio Demux"})
        events = reg.get_events(job_id)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "stage")

        # 5. Restart job
        restarted = reg.restart_job(job_id, phase="2")
        self.assertTrue(restarted)
        job_restarted = reg.get(job_id)
        self.assertEqual(job_restarted.state, "waiting_for_review")

        # Claim execution should succeed now
        claimed_phase_2 = reg.claim_execution(job_id)
        self.assertTrue(claimed_phase_2)

        # 6. Mark done
        reg.mark_done(job_id)
        self.assertTrue(reg.get(job_id).done)
        self.assertEqual(reg.get(job_id).state, "completed")

    def test_get_video_metadata_nonexistent(self):
        meta = get_video_metadata("nonexistent_file_abc.mp4")
        self.assertTrue(meta["error"])
        self.assertEqual(meta["duration"], "—")


if __name__ == "__main__":
    unittest.main()
