"""Small persistent, single-worker queue for personal Instagram uploads."""

from __future__ import annotations

import hashlib
import logging
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Optional

from modules.publisher_ig import InstagramUploadError, _state_dir, post_instagram_reel, validate_reel_video

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 3


class InstagramQueue:
    """SQLite-backed FIFO queue. One browser upload runs at a time."""

    def __init__(self, *, start_worker: bool = True) -> None:
        self.database = _state_dir() / "uploads.sqlite3"
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._initialize()
        self._worker: Optional[threading.Thread] = None
        if start_worker:
            self.start()

    def start(self) -> None:
        """Start the one local worker once; safe to call repeatedly."""
        if self._worker is None or not self._worker.is_alive():
            self._stop.clear()
            self._worker = threading.Thread(target=self._run, name="instagram-upload-worker", daemon=True)
            self._worker.start()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=30.0)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA journal_mode=WAL;")
            connection.execute("PRAGMA busy_timeout=15000;")
        except Exception:
            pass
        return connection

    @contextmanager
    def _database(self):
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._database() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS instagram_uploads (
                id TEXT PRIMARY KEY, video_path TEXT NOT NULL, video_hash TEXT NOT NULL,
                filename TEXT NOT NULL, caption TEXT NOT NULL, status TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0, error TEXT, reel_url TEXT,
                progress INTEGER NOT NULL DEFAULT 0, message TEXT NOT NULL DEFAULT '',
                created_at REAL NOT NULL, updated_at REAL NOT NULL, next_attempt_at REAL NOT NULL,
                share_clicked INTEGER NOT NULL DEFAULT 0, platform TEXT NOT NULL DEFAULT 'instagram',
                file_size INTEGER, duration REAL
            )""")
            columns = {row[1] for row in db.execute("PRAGMA table_info(instagram_uploads)").fetchall()}
            if "platform" not in columns:
                db.execute("ALTER TABLE instagram_uploads ADD COLUMN platform TEXT NOT NULL DEFAULT 'instagram'")
            if "file_size" not in columns:
                db.execute("ALTER TABLE instagram_uploads ADD COLUMN file_size INTEGER")
            if "duration" not in columns:
                db.execute("ALTER TABLE instagram_uploads ADD COLUMN duration REAL")
            if "queue_order" not in columns:
                db.execute("ALTER TABLE instagram_uploads ADD COLUMN queue_order REAL")
                db.execute("UPDATE instagram_uploads SET queue_order=rowid WHERE queue_order IS NULL")
            db.execute("CREATE INDEX IF NOT EXISTS idx_instagram_queue ON instagram_uploads(status, next_attempt_at)")
            db.execute("CREATE TABLE IF NOT EXISTS instagram_queue_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            db.execute("INSERT OR IGNORE INTO instagram_queue_settings(key, value) VALUES ('paused', '0')")
            db.execute("INSERT OR IGNORE INTO instagram_queue_settings(key, value) VALUES ('cooldown_seconds', '300')")
            db.execute("INSERT OR IGNORE INTO instagram_queue_settings(key, value) VALUES ('last_success_at', '0')")
            db.execute("""CREATE TABLE IF NOT EXISTS instagram_upload_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, upload_id TEXT NOT NULL,
                created_at REAL NOT NULL, event TEXT NOT NULL, detail TEXT NOT NULL
            )""")
            # Repair rows left retrying by older versions that had no hard cap.
            db.execute(
                "UPDATE instagram_uploads SET status='failed', message='Retry limit reached (3 attempts).', "
                "error=COALESCE(error, 'Retry limit reached'), updated_at=? "
                "WHERE status='retrying' AND attempts >= ?",
                (time.time(), MAX_ATTEMPTS),
            )
            # Recover orphaned uploads stuck in 'uploading' status
            db.execute(
                "UPDATE instagram_uploads SET status='queued', "
                "attempts=CASE WHEN attempts > 0 THEN attempts - 1 ELSE 0 END, "
                "message='Recovered after server restart.', updated_at=? "
                "WHERE status='uploading'",
                (time.time(),),
            )

    def _event(self, upload_id: str, event: str, detail: str) -> None:
        with self._lock, self._database() as db:
            db.execute(
                "INSERT INTO instagram_upload_events(upload_id, created_at, event, detail) VALUES (?, ?, ?, ?)",
                (upload_id, time.time(), event, detail[:4_000]),
            )

    @staticmethod
    def _hash(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for block in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    def enqueue(self, video_path: str, caption: str, *, allow_duplicate: bool = False) -> dict[str, Any]:
        duration = validate_reel_video(video_path)
        path = Path(video_path).resolve()
        video_hash = self._hash(path)
        now = time.time()
        with self._lock, self._database() as db:
            duplicate = db.execute(
                "SELECT id, status FROM instagram_uploads WHERE video_hash = ? AND status IN ('queued','uploading','retrying','completed','needs_manual_verification') ORDER BY created_at DESC LIMIT 1",
                (video_hash,),
            ).fetchone()
            if duplicate and not allow_duplicate:
                raise ValueError(f"This clip was already submitted (upload {duplicate['id']}, status {duplicate['status']}). Set allow_duplicate=true to override.")
            upload_id = str(uuid.uuid4())
            next_order = db.execute("SELECT COALESCE(MAX(queue_order), 0) + 1 FROM instagram_uploads").fetchone()[0]
            db.execute(
                "INSERT INTO instagram_uploads (id,video_path,video_hash,filename,caption,status,created_at,updated_at,next_attempt_at,file_size,duration,queue_order) VALUES (?,?,?,?,?,'queued',?,?,?,?,?,?)",
                (upload_id, str(path), video_hash, path.name, caption[:2_200], now, now, now, path.stat().st_size, duration, next_order),
            )
            # Snapshot the row while we still hold the lock so the worker
            # thread (which also requires self._lock to claim work) cannot
            # race ahead and mutate/complete it before we return it below.
            row = db.execute("SELECT * FROM instagram_uploads WHERE id = ?", (upload_id,)).fetchone()
        self._wake.set()
        self._event(upload_id, "queued", "Added to Instagram queue")
        return dict(row) if row else {}

    def get(self, upload_id: str) -> Optional[dict[str, Any]]:
        with self._database() as db:
            row = db.execute("SELECT * FROM instagram_uploads WHERE id = ?", (upload_id,)).fetchone()
        return dict(row) if row else None

    def events(self, upload_id: str) -> list[dict[str, Any]]:
        with self._database() as db:
            rows = db.execute("SELECT created_at, event, detail FROM instagram_upload_events WHERE upload_id=? ORDER BY id", (upload_id,)).fetchall()
        return [dict(row) for row in rows]

    def history(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._database() as db:
            rows = db.execute("SELECT * FROM instagram_uploads ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    def summary(self) -> dict[str, Any]:
        with self._database() as db:
            rows = db.execute("SELECT status, COUNT(*) AS count FROM instagram_uploads GROUP BY status").fetchall()
            paused = db.execute("SELECT value FROM instagram_queue_settings WHERE key='paused'").fetchone()
            cooldown = db.execute("SELECT value FROM instagram_queue_settings WHERE key='cooldown_seconds'").fetchone()
            last_success = db.execute("SELECT value FROM instagram_queue_settings WHERE key='last_success_at'").fetchone()
        return {
            "paused": bool(paused and paused["value"] == "1"),
            "cooldown_seconds": int(cooldown["value"]) if cooldown else 300,
            "last_success_at": float(last_success["value"]) if last_success else 0.0,
            "counts": {row["status"]: row["count"] for row in rows}
        }

    def set_paused(self, paused: bool) -> None:
        with self._lock, self._database() as db:
            db.execute("UPDATE instagram_queue_settings SET value=? WHERE key='paused'", ("1" if paused else "0",))
        if not paused:
            self._wake.set()

    def set_cooldown(self, seconds: int) -> None:
        with self._lock, self._database() as db:
            db.execute("UPDATE instagram_queue_settings SET value=? WHERE key='cooldown_seconds'", (str(seconds),))

    def retry(self, upload_id: str) -> Optional[dict[str, Any]]:
        item = self.get(upload_id)
        retryable_states = {"failed", "login_required", "challenge_required", "rate_limited", "rejected", "needs_manual_verification"}
        if not item or item["status"] not in retryable_states:
            return None
        self._update(upload_id, status="queued", attempts=0, error=None, progress=0, message="Queued for manual retry", next_attempt_at=time.time())
        self._event(upload_id, "manual_retry", "User requeued upload")
        self._wake.set()
        return self.get(upload_id)

    def remove(self, upload_id: str) -> bool:
        item = self.get(upload_id)
        if not item or item["status"] == "uploading":
            return False
        with self._lock, self._database() as db:
            db.execute("DELETE FROM instagram_upload_events WHERE upload_id=?", (upload_id,))
            return db.execute("DELETE FROM instagram_uploads WHERE id=?", (upload_id,)).rowcount > 0

    def clear(self, statuses: set[str]) -> int:
        if not statuses:
            return 0
        placeholders = ",".join("?" for _ in statuses)
        with self._lock, self._database() as db:
            ids = [row[0] for row in db.execute(f"SELECT id FROM instagram_uploads WHERE status IN ({placeholders})", tuple(statuses)).fetchall()]
            if ids:
                marks = ",".join("?" for _ in ids)
                db.execute(f"DELETE FROM instagram_upload_events WHERE upload_id IN ({marks})", tuple(ids))
            return db.execute(f"DELETE FROM instagram_uploads WHERE status IN ({placeholders})", tuple(statuses)).rowcount

    def mark_completed(self, upload_id: str) -> Optional[dict[str, Any]]:
        item = self.get(upload_id)
        if not item or item["status"] != "needs_manual_verification":
            return None
        self._update(upload_id, status="completed", progress=100, message="Marked completed after manual verification", error=None)
        self._event(upload_id, "manual_completion", "User confirmed Reel exists")
        return self.get(upload_id)

    def cancel(self, upload_id: str) -> Optional[dict[str, Any]]:
        item = self.get(upload_id)
        if not item or item["status"] not in {"queued", "retrying"}:
            return None
        self._update(upload_id, status="cancelled", message="Cancelled before upload started")
        self._event(upload_id, "cancelled", "User cancelled queued upload")
        return self.get(upload_id)

    def move(self, upload_id: str, direction: int) -> Optional[dict[str, Any]]:
        item = self.get(upload_id)
        if not item or item["status"] not in {"queued", "retrying"} or direction not in {-1, 1}:
            return None
        with self._lock, self._database() as db:
            rows = db.execute("SELECT id, queue_order FROM instagram_uploads WHERE status IN ('queued','retrying') ORDER BY queue_order, created_at").fetchall()
            index = next((i for i, row in enumerate(rows) if row["id"] == upload_id), None)
            if index is None or not 0 <= index + direction < len(rows):
                return None
            other = rows[index + direction]
            db.execute("UPDATE instagram_uploads SET queue_order=?, updated_at=? WHERE id=?", (other["queue_order"], time.time(), upload_id))
            db.execute("UPDATE instagram_uploads SET queue_order=?, updated_at=? WHERE id=?", (item["queue_order"], time.time(), other["id"]))
        self._event(upload_id, "reordered", "Moved up" if direction < 0 else "Moved down")
        return self.get(upload_id)

    def _update(self, upload_id: str, **values: Any) -> None:
        values["updated_at"] = time.time()
        columns = ", ".join(f"{key} = ?" for key in values)
        with self._lock, self._database() as db:
            db.execute(f"UPDATE instagram_uploads SET {columns} WHERE id = ?", (*values.values(), upload_id))

    def _claim_next(self) -> Optional[dict[str, Any]]:
        with self._lock, self._database() as db:
            paused = db.execute("SELECT value FROM instagram_queue_settings WHERE key='paused'").fetchone()
            if paused and paused["value"] == "1":
                return None
            
            # Cooldown check to prevent spam rate limits on consecutive uploads
            cooldown_row = db.execute("SELECT value FROM instagram_queue_settings WHERE key='cooldown_seconds'").fetchone()
            cooldown_seconds = float(cooldown_row["value"]) if cooldown_row else 300.0
            last_success_row = db.execute("SELECT value FROM instagram_queue_settings WHERE key='last_success_at'").fetchone()
            last_success_at = float(last_success_row["value"]) if last_success_row else 0.0
            now = time.time()
            if now - last_success_at < cooldown_seconds:
                return None
            
            row = db.execute(
                "SELECT * FROM instagram_uploads WHERE status IN ('queued','retrying') AND attempts < ? AND next_attempt_at <= ? ORDER BY queue_order, created_at LIMIT 1",
                (MAX_ATTEMPTS, now),
            ).fetchone()
            if not row:
                return None
            db.execute(
                "UPDATE instagram_uploads SET status='uploading', attempts=attempts+1, progress=1, message='Starting browser upload', updated_at=? WHERE id=?",
                (now, row["id"]),
            )
            claimed = dict(row)
            claimed["attempts"] += 1
            return claimed

    def _run(self) -> None:
        while not self._stop.is_set():
            item = self._claim_next()
            if item is None:
                self._wake.wait(timeout=5)
                self._wake.clear()
                continue
            upload_id = item["id"]
            started_at = time.time()
            self._update(upload_id, message=f"Uploading... Attempt {item['attempts']}/{MAX_ATTEMPTS}")
            self._event(upload_id, "uploading", f"Attempt {item['attempts']}/{MAX_ATTEMPTS} started")
            logger.info("[InstagramQueue] Uploading %s (attempt %s/%s)", item["filename"], item["attempts"], MAX_ATTEMPTS)
            try:
                result = post_instagram_reel(
                    item["video_path"], item["caption"],
                    progress=lambda percent, message: self._update(upload_id, progress=percent, message=message),
                )
                self._update(upload_id, status=result.status, progress=100, message=result.status.replace("_", " "), reel_url=result.reel_url, error=None)
                self._event(upload_id, result.status, result.status.replace("_", " "))
                if result.status in {"completed", "needs_manual_verification"}:
                    with self._lock, self._database() as db:
                        db.execute("UPDATE instagram_queue_settings SET value=? WHERE key='last_success_at'", (str(time.time()),))
            except InstagramUploadError as exc:
                elapsed = time.time() - started_at
                if exc.retryable and not exc.share_clicked and item["attempts"] < MAX_ATTEMPTS:
                    delay = 2 ** (item["attempts"] - 1) * 30
                    next_attempt = item["attempts"] + 1
                    message = f"Retry {item['attempts']}/{MAX_ATTEMPTS} in {delay}s (next attempt {next_attempt}/{MAX_ATTEMPTS}): {exc}"
                    self._update(upload_id, status="retrying", message=message, error=str(exc), next_attempt_at=time.time() + delay)
                    self._event(upload_id, "retrying", message)
                    logger.warning("[InstagramQueue] retry=%s/%s next_attempt=%s/%s timestamp=%.3f elapsed=%.2fs reason=%s exception=%r", item["attempts"], MAX_ATTEMPTS, next_attempt, MAX_ATTEMPTS, time.time(), elapsed, exc, exc)
                else:
                    status = "needs_manual_verification" if exc.share_clicked else exc.status
                    message = str(exc)
                    if exc.retryable and item["attempts"] >= MAX_ATTEMPTS:
                        message = f"Failed after {MAX_ATTEMPTS} attempts: {exc}"
                    self._update(upload_id, status=status, message=message, error=str(exc), share_clicked=int(exc.share_clicked))
                    self._event(upload_id, status, message)
                    logger.error("[InstagramQueue] Upload %s ended as %s: %s", upload_id, status, message)
                    # Auto-pause queue on persistent blocking failures
                    if status in {"login_required", "challenge_required", "rate_limited"}:
                        self.set_paused(True)
                        logger.warning("[InstagramQueue] Auto-paused queue due to persistent blocking failure: %s", status)
            except Exception as exc:
                self._update(upload_id, status="failed", message=str(exc), error=str(exc))
                self._event(upload_id, "failed", str(exc))
                logger.exception("[InstagramQueue] Unexpected failure for %s", upload_id)

    def stop(self) -> None:
        """Stop a queue worker cleanly; primarily useful for shutdown and tests."""
        self._stop.set()
        self._wake.set()
        if self._worker is not None:
            self._worker.join(timeout=5)


_queue: Optional[InstagramQueue] = None
_queue_lock = threading.Lock()


def get_instagram_queue(*, start_worker: bool = True) -> InstagramQueue:
    """Return the process-wide queue; child pipeline processes can enqueue only."""
    global _queue
    with _queue_lock:
        if _queue is None:
            _queue = InstagramQueue(start_worker=start_worker)
        elif start_worker:
            _queue.start()
        return _queue
