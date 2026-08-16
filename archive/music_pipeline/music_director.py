"""Local soundtrack selection for dialogue-first self-improvement clips.

The Music folder is deliberately treated as a small editorial library, not as
an unrestricted playlist.  Filename keywords give useful automatic tags while
``Music/music_library.json`` can optionally override them as the collection
grows.
"""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}

# These are deliberately conservative. Self-improvement videos should never
# accidentally acquire thriller, sad, or high-intensity emotional framing.
UNSUITABLE_TERMS = {
    "dark", "darkness", "mystery", "drama", "dramatic", "horror",
    "suspense", "sad", "melancholy", "melancholic", "tension", "tense",
    "aggressive", "intense", "epic", "battle", "trap", "phonk",
}

MOOD_TERMS = {
    "warm_reflection": {"warm", "peace", "peaceful", "calm", "soft", "gentle", "piano", "ambient"},
    "calm_focus": {"calm", "soft", "ambient", "focus", "lofi", "minimal", "corporate"},
    "measured_momentum": {"uplifting", "inspire", "motivational", "positive", "success", "corporate", "ambient"},
}


class MusicDirector:
    """Chooses a safe local track and an excerpt suitable for one clip."""

    def __init__(self, music_dir: str | Path):
        self.music_dir = Path(music_dir)
        self.overrides = self._load_overrides()

    def choose(
        self,
        *,
        clip: Dict[str, Any],
        clip_words: Iterable[Dict[str, Any]],
        clip_duration_s: float,
        used_paths: Set[str],
    ) -> Optional[Dict[str, Any]]:
        """Return a render-ready music choice, or None when no safe track exists."""
        candidates = self._library_entries()
        if not candidates:
            logger.warning("[MusicDirector] No audio files found in %s.", self.music_dir)
            return None

        mood = self._normalise_mood(clip.get("music_mood"), clip, clip_words)
        scored = []
        for entry in candidates:
            if not entry["enabled"] or entry["unsafe"]:
                continue
            score = self._score(entry, mood, used_paths)
            scored.append((score, entry))

        if not scored:
            logger.warning("[MusicDirector] The library has no safe music for a self-improvement clip.")
            return None

        # Stable ordering makes a rerun reproducible, while the used-path
        # penalty spreads an eight-clip batch across the available library.
        scored.sort(key=lambda item: (item[0], item[1]["name"]), reverse=True)
        _, chosen = scored[0]
        start_s = self._choose_excerpt_start(chosen, clip, clip_duration_s)

        return {
            "path": str(chosen["path"]),
            "name": chosen["name"],
            "mood": mood,
            "start_s": start_s,
            "duration_s": chosen["duration_s"],
            "reason": f"{mood.replace('_', ' ')} match from local Music library",
        }

    def _library_entries(self) -> List[Dict[str, Any]]:
        if not self.music_dir.exists():
            return []

        entries = []
        for path in self.music_dir.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            override = self.overrides.get(path.name, {})
            searchable = f"{path.stem} {' '.join(override.get('tags', []))}".lower()
            tags = set(_words(searchable))
            unsafe = bool(tags & UNSUITABLE_TERMS) and not bool(override.get("allow_dark_mood", False))
            duration_s = _probe_duration(path)
            if duration_s <= 2.0:
                logger.warning("[MusicDirector] Skipping unreadable or very short file: %s", path.name)
                continue
            entries.append({
                "path": path,
                "name": path.name,
                "tags": tags,
                "duration_s": duration_s,
                "enabled": override.get("enabled", True),
                "unsafe": unsafe,
                "moods": set(override.get("moods", [])),
                "start_offset_s": max(0.0, float(override.get("start_offset_s", 0.0))),
            })
        return entries

    def _load_overrides(self) -> Dict[str, Dict[str, Any]]:
        manifest = self.music_dir / "music_library.json"
        if not manifest.exists():
            return {}
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("the root must be an object")
            return {str(name): value for name, value in data.items() if isinstance(value, dict)}
        except Exception as exc:
            logger.warning("[MusicDirector] Ignoring invalid music_library.json: %s", exc)
            return {}

    @staticmethod
    def _normalise_mood(
        supplied_mood: Any,
        clip: Dict[str, Any],
        clip_words: Iterable[Dict[str, Any]],
    ) -> str:
        allowed = set(MOOD_TERMS)
        if supplied_mood in allowed:
            return supplied_mood

        text = " ".join(str(w.get("word", "")) for w in clip_words).lower()
        text += " " + str(clip.get("title", "")).lower() + " " + str(clip.get("reason", "")).lower()
        if any(word in text for word in ("pain", "struggle", "lonely", "fear", "healing", "grief", "vulnerable")):
            return "warm_reflection"
        if any(word in text for word in ("start", "action", "discipline", "habit", "goal", "change", "build", "win")):
            return "measured_momentum"
        return "calm_focus"

    @staticmethod
    def _score(entry: Dict[str, Any], mood: str, used_paths: Set[str]) -> int:
        score = 20
        score += 30 if mood in entry["moods"] else 0
        score += 9 * len(entry["tags"] & MOOD_TERMS[mood])
        score += 4 * len(entry["tags"] & {"calm", "soft", "ambient", "peace", "gentle", "minimal"})
        if str(entry["path"]) in used_paths:
            score -= 35
        return score

    @staticmethod
    def _choose_excerpt_start(entry: Dict[str, Any], clip: Dict[str, Any], clip_duration_s: float) -> float:
        """Pick a repeatable, non-abrupt excerpt; fades handle its boundaries.

        The first use starts at the producer's intended introduction. Reuses
        choose a later section when the track is long enough, avoiding the same
        audible segment on every clip in a batch.
        """
        max_start = max(0.0, entry["duration_s"] - min(clip_duration_s, entry["duration_s"]))
        if max_start < 12.0:
            return min(entry["start_offset_s"], max_start)
        seed = f"{entry['name']}|{clip.get('title', '')}|{clip.get('start_ms', 0)}"
        fraction = int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8], 16) / 0xFFFFFFFF
        # Preserve the opening on some clips; otherwise use a later, safe room
        # in the track. The renderer applies 0.8s/1.3s fades at both boundaries.
        return round(min(max_start, entry["start_offset_s"] + fraction * max_start), 3)


def _words(value: str) -> List[str]:
    import re
    return re.findall(r"[a-z]+", value.lower())


def _probe_duration(path: Path) -> float:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            text=True,
        )
        return float(result.stdout.strip())
    except Exception as exc:
        logger.warning("[MusicDirector] Could not inspect %s: %s", path.name, exc)
        return 0.0
