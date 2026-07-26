import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

@dataclass
class Job:
    job_id: str
    path: str
    filename: str
    start_time: float = field(default_factory=time.time)
    process: object = None
    done: bool = False

class JobRegistry:
    """Thread-safe job registry with auto-TTL eviction."""
    _MAX_AGE_HOURS = 24
    
    def __init__(self):
        self._jobs: Dict[str, Job] = {}
        self._events: Dict[str, List] = {}
        self._configs: Dict[str, dict] = {}
    
    def register(self, job_id: str, path: str, filename: str) -> Job:
        job = Job(job_id=job_id, path=path, filename=filename)
        self._jobs[job_id] = job
        self._events[job_id] = []
        return job

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def set_config(self, job_id: str, config: dict):
        self._configs[job_id] = config

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
        return len(stale_ids)

registry = JobRegistry()
