import os
import hashlib
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Set, Iterable

from modules.bg_music import scan_music_directories, KNOWN_TRACK_METADATA

logger = logging.getLogger("ClipHub.MusicDirector")

MOOD_KEYWORDS = {
    "warm_reflection": [
        "pain", "struggle", "lonely", "fear", "healing", "grief", "vulnerable",
        "anxiety", "overwhelm", "tired", "sad", "lost", "empty", "shame", "doubt",
        "forgive", "heart", "broken", "emotion", "feeling", "childhood"
    ],
    "measured_momentum": [
        "start", "action", "discipline", "habit", "goal", "change", "build", "win",
        "execute", "morning", "routine", "power", "growth", "progress", "unstoppable",
        "momentum", "workout", "effort", "system", "daily", "consistency"
    ],
    "deep_insight": [
        "truth", "reframe", "realize", "paradigm", "shift", "secret", "why",
        "pattern", "trap", "illusion", "mechanism", "reason", "understand", "mindset"
    ],
    "calm_focus": [
        "focus", "deep work", "sleep", "brain", "neuroscience", "dopamine", "clarity",
        "calm", "attention", "distraction", "reset", "memory", "peace", "learning"
    ]
}


class MusicDirector:
    """
    Intelligently selects and sequences background music tracks for ClipHub clips.
    Matches the emotional arc of Kai and the podcast speaker while avoiding repetition.
    """

    def __init__(self, base_volume: float = 0.14):
        self.base_volume = base_volume
        self.used_paths: Set[str] = set()

    def choose_track(
        self,
        clip: Dict[str, Any],
        clip_words: Optional[Iterable[Dict[str, Any]]] = None,
        clip_duration_s: float = 45.0,
        volume: Optional[float] = None,
        explicit_choice: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Chooses an optimal background soundtrack for a clip.
        Returns a render-ready dictionary with path, start_s, volume, and fades.
        """
        vol = volume if volume is not None else self.base_volume
        tracks = scan_music_directories()

        if not tracks:
            logger.warning("[MusicDirector] No background music tracks available.")
            return None

        # 1. Handle explicit track override
        if explicit_choice and explicit_choice.lower() not in ("auto", "none", "off", "false", ""):
            for t in tracks:
                if (t["filename"].lower() == explicit_choice.lower() or 
                    explicit_choice.lower() in t["name"].lower() or 
                    explicit_choice.lower() in t["filename"].lower()):
                    start_s = self._calculate_excerpt_start(t, clip, clip_duration_s)
                    return {
                        "path": t["path"],
                        "name": t["name"],
                        "mood": t["moods"][0] if t["moods"] else "custom",
                        "start_s": start_s,
                        "volume": vol,
                        "fade_in_s": 0.8,
                        "fade_out_s": 1.2,
                        "reason": f"Explicitly chosen track: {t['name']}"
                    }

        # 2. Analyze clip to determine the dominant emotional mood
        mood = self._detect_mood(clip, clip_words)

        # 3. Score all candidate tracks
        scored = []
        for t in tracks:
            score = self._score_track(t, mood, self.used_paths)
            scored.append((score, t))

        if not scored:
            return None

        # Sort descending by score; break ties deterministically
        scored.sort(key=lambda x: (x[0], x[1]["name"]), reverse=True)
        _, chosen = scored[0]

        self.used_paths.add(chosen["path"])
        start_s = self._calculate_excerpt_start(chosen, clip, clip_duration_s)

        logger.info(f"[MusicDirector] 🎵 Assigned '{chosen['name']}' (Mood: {mood}, Start: {start_s:.1f}s, Vol: {vol:.2f})")

        return {
            "path": chosen["path"],
            "name": chosen["name"],
            "mood": mood,
            "start_s": start_s,
            "volume": vol,
            "fade_in_s": 0.8,
            "fade_out_s": 1.2,
            "reason": f"Matched '{mood.replace('_', ' ')}' mood for clip"
        }

    def _detect_mood(self, clip: Dict[str, Any], clip_words: Optional[Iterable[Dict[str, Any]]]) -> str:
        """Determines the mood from clip metadata, kai_why, hook_explanation, and spoken text."""
        # Check explicit mood
        if clip.get("music_mood") in MOOD_KEYWORDS:
            return clip["music_mood"]

        text_parts = [
            str(clip.get("title", "")),
            str(clip.get("hook_explanation", "")),
            str(clip.get("kai_why", "")),
            str(clip.get("hook_type", "")),
        ]
        if clip_words:
            text_parts.append(" ".join(str(w.get("word", "")) for w in clip_words))

        combined_text = " ".join(text_parts).lower()

        scores = {mood: 0 for mood in MOOD_KEYWORDS}
        for mood, kws in MOOD_KEYWORDS.items():
            for kw in kws:
                if kw in combined_text:
                    scores[mood] += 1

        # Determine highest scoring mood
        best_mood = max(scores, key=scores.get)
        if scores[best_mood] > 0:
            return best_mood

        # Default fallback
        return "calm_focus"

    def _score_track(self, track: Dict[str, Any], mood: str, used_paths: Set[str]) -> int:
        """Scores a track based on mood alignment and penalizes recent reuse."""
        score = 20
        track_moods = track.get("moods", [])
        track_tags = track.get("tags", [])

        if mood in track_moods:
            score += 40

        # Bonus for relevant tags
        if mood == "warm_reflection" and any(tag in track_tags for tag in ("piano", "reflection", "gentle", "emotional")):
            score += 25
        elif mood == "measured_momentum" and any(tag in track_tags for tag in ("momentum", "growth", "inspirational", "pulse")):
            score += 25
        elif mood == "calm_focus" and any(tag in track_tags for tag in ("ambient", "focus", "cinematic", "calm")):
            score += 25
        elif mood == "deep_insight" and any(tag in track_tags for tag in ("documentary", "thoughtful", "reflection", "cinematic")):
            score += 25

        # Penalty if already used in this batch
        if track["path"] in used_paths:
            score -= 45

        return score

    def _calculate_excerpt_start(self, track: Dict[str, Any], clip: Dict[str, Any], clip_duration_s: float) -> float:
        """
        Calculates a clean excerpt start offset within the track.
        Uses deterministic hashing from clip properties so re-renders are stable.
        """
        track_dur = track.get("duration_s", 60.0)
        base_offset = track.get("start_offset_s", 0.0)
        max_start = max(0.0, track_dur - min(clip_duration_s, track_dur) - 2.0)

        if max_start < 8.0:
            return base_offset

        # Deterministic pseudo-random seed based on clip title and start time
        seed = f"{track['filename']}_{clip.get('title', '')}_{clip.get('start_ms', 0)}"
        hash_val = int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8], 16) / 0xFFFFFFFF
        start_offset = base_offset + (hash_val * (max_start - base_offset))
        return round(min(max_start, max(base_offset, start_offset)), 2)
