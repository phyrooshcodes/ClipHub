import json
import os
import time
import threading
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)
JOURNAL_PATH = Path(__file__).parent.parent / "temp" / ".jobs_journal.json"

import subprocess
import sys

@dataclass
class Job:
    job_id: str
    path: str
    filename: str
    start_time: float = field(default_factory=time.time)
    execution_start_time: float = field(default_factory=time.time)
    process: object = None
    done: bool = False
    started: bool = False
    state: str = "created"  # created, phase_1_running, waiting_for_review, phase_2_running, completed, failed, cancelled

class JobRegistry:
    """Thread-safe synchronized job registry with auto-TTL eviction and disk journal persistence."""
    _MAX_AGE_HOURS = 24
    
    def __init__(self):
        self._lock = threading.RLock()
        self._jobs: Dict[str, Job] = {}
        self._events: Dict[str, List] = {}
        self._configs: Dict[str, dict] = {}
        self._load_journal()
    
    def _save_journal(self):
        try:
            JOURNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "jobs": {
                    jid: {
                        "job_id": j.job_id,
                        "path": j.path,
                        "filename": j.filename,
                        "start_time": j.start_time,
                        "execution_start_time": j.execution_start_time,
                        "done": j.done,
                        "started": j.started,
                        "state": getattr(j, "state", "created")
                    }
                    for jid, j in self._jobs.items()
                },
                "configs": self._configs,
                "events": {jid: evs[-50:] for jid, evs in self._events.items()}
            }
            # Write to temporary file first then replace atomically
            temp_journal = JOURNAL_PATH.with_suffix(".tmp")
            with open(temp_journal, "w", encoding="utf-8") as f:
                json.dump(data, f)
            if temp_journal.exists():
                temp_journal.replace(JOURNAL_PATH)
        except Exception as e:
            logger.debug(f"[JobRegistry] Journal save notice: {e}")

    def _load_journal(self):
        with self._lock:
            if not JOURNAL_PATH.exists():
                return
            try:
                with open(JOURNAL_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                now = time.time()
                max_age_sec = self._MAX_AGE_HOURS * 3600
                for jid, jdata in data.get("jobs", {}).items():
                    if now - jdata.get("start_time", 0) < max_age_sec:
                        was_done = jdata.get("done", True)
                        self._jobs[jid] = Job(
                            job_id=jdata["job_id"],
                            path=jdata["path"],
                            filename=jdata["filename"],
                            start_time=jdata.get("start_time", now),
                            execution_start_time=jdata.get("execution_start_time", jdata.get("start_time", now)),
                            done=was_done,
                            started=was_done,
                            state=jdata.get("state", "completed" if was_done else "created")
                        )
                self._configs = data.get("configs", {})
                self._events = data.get("events", {})
            except Exception as e:
                logger.debug(f"[JobRegistry] Journal load notice: {e}")

    def register(self, job_id: str, path: str, filename: str) -> Job:
        with self._lock:
            job = Job(job_id=job_id, path=path, filename=filename)
            self._jobs[job_id] = job
            self._events[job_id] = []
            self._save_journal()
            return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def set_config(self, job_id: str, config: dict):
        with self._lock:
            self._configs[job_id] = config
            self._save_journal()

    def get_config(self, job_id: str) -> dict:
        with self._lock:
            return dict(self._configs.get(job_id, {}))

    def add_event(self, job_id: str, event: dict):
        with self._lock:
            if job_id not in self._events:
                self._events[job_id] = []
            self._events[job_id].append(event)
            # Bound in-memory event buffer to last 200 events to prevent runtime heap accumulation
            if len(self._events[job_id]) > 200:
                self._events[job_id] = self._events[job_id][-200:]
            # Persist major milestone events to journal
            if event.get("type") in ("start", "done", "error", "phase", "review", "phase_1_complete"):
                self._save_journal()

    def get_events(self, job_id: str) -> List[dict]:
        with self._lock:
            return list(self._events.get(job_id, []))

    def set_state(self, job_id: str, state: str):
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.state = state
                if state in ("completed", "failed", "cancelled"):
                    job.done = True
                self._save_journal()

    def mark_done(self, job_id: str):
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].done = True
                self._jobs[job_id].state = "completed"
                self._save_journal()

    def claim_execution(self, job_id: str) -> bool:
        """Atomically claims execution authority for a job, preventing duplicate subprocess launches."""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return False
            config = self._configs.get(job_id, {})
            force_restart = config.pop("force_restart", False)
            if force_restart or not job.started:
                job.started = True
                job.done = False
                phase = config.get("phase", "1")
                job.state = "phase_2_running" if phase == "2" else "phase_1_running"
                job.execution_start_time = time.time()
                if force_restart:
                    self._events[job_id] = []
                self._save_journal()
                return True
            return False

    def restart_job(self, job_id: str, phase: str = "2") -> bool:
        """Safely terminates active child subprocess if running, and atomically prepares job for next phase."""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return False
            # Safely terminate any active child process
            if job.process and getattr(job.process, "returncode", None) is None:
                pid = getattr(job.process, "pid", None)
                try:
                    if sys.platform == "win32" and pid:
                        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, timeout=5)
                    else:
                        job.process.terminate()
                except Exception as e:
                    logger.warning(f"Error terminating child process {pid}: {e}")
                
                # Check if process actually terminated
                if hasattr(job.process, "poll") and job.process.poll() is None:
                    try:
                        job.process.kill()
                    except Exception:
                        pass
                
                job.process = None
                
            self._events[job_id] = []
            job.done = False
            job.started = False
            job.state = "waiting_for_review" if phase == "2" else "created"
            job.execution_start_time = time.time()
            config = self._configs.get(job_id, {})
            config["force_restart"] = True
            config["phase"] = phase
            self._configs[job_id] = config
            self._save_journal()
            return True

    def evict_stale(self) -> int:
        with self._lock:
            now = time.time()
            cutoff = now - (self._MAX_AGE_HOURS * 3600)
            stale = [jid for jid, j in self._jobs.items() if j.start_time < cutoff]
            for jid in stale:
                self._jobs.pop(jid, None)
                self._events.pop(jid, None)
                self._configs.pop(jid, None)
            if stale:
                logger.info(f"Evicted {len(stale)} stale jobs from registry.")
                self._save_journal()
            return len(stale)

    def all_jobs(self) -> List[Job]:
        with self._lock:
            return list(self._jobs.values())

registry = JobRegistry()
