import json
import os
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)
JOURNAL_PATH = Path(__file__).parent.parent / "temp" / ".jobs_journal.json"

@dataclass
class Job:
    job_id: str
    path: str
    filename: str
    start_time: float = field(default_factory=time.time)
    process: object = None
    done: bool = False

class JobRegistry:
    """Thread-safe job registry with auto-TTL eviction and disk journal persistence."""
    _MAX_AGE_HOURS = 24
    
    def __init__(self):
        self._jobs: Dict[str, Job] = {}
        self._events: Dict[str, List] = {}
        self._configs: Dict[str, dict] = {}
        self._load_journal()
    
    def _save_journal(self):
        try:
            JOURNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "jobs": {
                    jid: {"job_id": j.job_id, "path": j.path, "filename": j.filename, "start_time": j.start_time, "done": j.done}
                    for jid, j in self._jobs.items()
                },
                "configs": self._configs,
                "events": {jid: evs[-50:] for jid, evs in self._events.items()} # keep last 50 events per job
            }
            with open(JOURNAL_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception as e:
            logger.debug(f"[JobRegistry] Journal save notice: {e}")

    def _load_journal(self):
        if not JOURNAL_PATH.exists():
            return
        try:
            with open(JOURNAL_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            now = time.time()
            max_age_sec = self._MAX_AGE_HOURS * 3600
            for jid, jdata in data.get("jobs", {}).items():
                if now - jdata.get("start_time", 0) < max_age_sec:
                    self._jobs[jid] = Job(
                        job_id=jdata["job_id"],
                        path=jdata["path"],
                        filename=jdata["filename"],
                        start_time=jdata.get("start_time", now),
                        done=jdata.get("done", True)
                    )
            self._configs = data.get("configs", {})
            self._events = data.get("events", {})
        except Exception as e:
            logger.debug(f"[JobRegistry] Journal load notice: {e}")

    def register(self, job_id: str, path: str, filename: str) -> Job:
        job = Job(job_id=job_id, path=path, filename=filename)
        self._jobs[job_id] = job
        self._events[job_id] = []
        self._save_journal()
        return job

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def set_config(self, job_id: str, config: dict):
        self._configs[job_id] = config
        self._save_journal()

    def get_config(self, job_id: str) -> dict:
        return self._configs.get(job_id, {})

    def add_event(self, job_id: str, event: dict):
        if job_id not in self._events:
            self._events[job_id] = []
        self._events[job_id].append(event)

    def get_events(self, job_id: str) -> List[dict]:
        return self._events.get(job_id, [])

    def mark_done(self, job_id: str):
        if job_id in self._jobs:
            self._jobs[job_id].done = True
            self._save_journal()

    def evict_stale(self) -> int:
        now = time.time()
        max_age_sec = self._MAX_AGE_HOURS * 3600
        stale_ids = [
            jid for jid, job in self._jobs.items() 
            if now - job.start_time > max_age_sec
        ]
        for jid in stale_ids:
            del self._jobs[jid]
            if jid in self._events:
                del self._events[jid]
            if jid in self._configs:
                del self._configs[jid]
        
        if stale_ids:
            logger.info(f"Evicted {len(stale_ids)} stale jobs from registry.")
            self._save_journal()
        return len(stale_ids)

registry = JobRegistry()
