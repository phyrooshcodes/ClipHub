import os
import json
import logging
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger("ClipHub.BgMusic")

# Primary and fallback music directories
REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MUSIC_DIRS = [
    REPO_ROOT / "assets" / "music",
    Path(os.environ.get("CLIPHUB_MUSIC_DIR", r"C:\Users\Qwen\Downloads\ClipHubBGM")),
    REPO_ROOT / "Music",
]

SUPPORTED_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}

# Curated metadata for known tracks
KNOWN_TRACK_METADATA = {
    "the_mountain-piano-documentary-567436.mp3": {
        "name": "The Mountain — Piano Reflection",
        "moods": ["warm_reflection", "deep_insight", "emotional", "calm_focus"],
        "tags": ["piano", "documentary", "reflection", "calm", "gentle", "mindset", "self-improvement"],
        "start_offset_s": 0.0,
    },
    "atlasaudio-documentary-581913.mp3": {
        "name": "Atlas Audio — Documentary Atmosphere",
        "moods": ["calm_focus", "deep_insight", "measured_momentum"],
        "tags": ["ambient", "documentary", "cinematic", "focus", "clarity", "learning"],
        "start_offset_s": 0.0,
    },
    "monume-documentary-documentary-music-547923.mp3": {
        "name": "Monume — Documentary Reflection",
        "moods": ["warm_reflection", "calm_focus", "inspirational"],
        "tags": ["reflection", "documentary", "thoughtful", "piano", "insight"],
        "start_offset_s": 0.0,
    },
    "the_mountain-documentary-documentary-music-508000.mp3": {
        "name": "The Mountain — Documentary Momentum",
        "moods": ["measured_momentum", "inspirational", "action"],
        "tags": ["inspirational", "documentary", "momentum", "growth", "discipline", "action"],
        "start_offset_s": 0.0,
    },
    "sigmamusicart-documentary-556020.mp3": {
        "name": "Sigma Music — Documentary Pulse",
        "moods": ["calm_focus", "measured_momentum", "deep_insight"],
        "tags": ["pulse", "documentary", "focus", "habits", "discipline", "flow"],
        "start_offset_s": 0.0,
    },
}


def probe_audio_duration(path: Path | str) -> float:
    """Get precise duration of an audio file in seconds via ffprobe."""
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path)
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return float(result.stdout.strip())
    except Exception as exc:
        logger.warning(f"[BgMusic] Could not probe duration for {path}: {exc}")
        return 0.0


def scan_music_directories() -> List[Dict[str, Any]]:
    """
    Scans all registered music directories for valid audio files.
    Returns a deduplicated list of track objects with metadata.
    """
    found_tracks: Dict[str, Dict[str, Any]] = {}

    for m_dir in DEFAULT_MUSIC_DIRS:
        if not m_dir.exists():
            continue

        for p in m_dir.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue

            fname = p.name
            if fname in found_tracks:
                continue

            dur = probe_audio_duration(p)
            if dur < 3.0:
                continue

            meta = KNOWN_TRACK_METADATA.get(fname, {})
            display_name = meta.get("name", p.stem.replace("-", " ").replace("_", " ").title())
            moods = meta.get("moods", ["calm_focus"])
            tags = meta.get("tags", [p.stem.lower()])

            found_tracks[fname] = {
                "filename": fname,
                "name": display_name,
                "path": str(p.resolve()),
                "duration_s": dur,
                "moods": moods,
                "tags": tags,
                "start_offset_s": meta.get("start_offset_s", 0.0)
            }

    return list(found_tracks.values())


def get_music_track(choice: str) -> Optional[str]:
    """
    Get absolute path to a background music file based on user choice or filename.
    """
    if not choice or choice.lower() in ("none", "off", "0", "false"):
        return None

    tracks = scan_music_directories()
    if not tracks:
        logger.warning("[BgMusic] No music tracks found in registered directories.")
        return None

    # Exact filename match
    for t in tracks:
        if t["filename"].lower() == choice.lower() or t["name"].lower() == choice.lower():
            return t["path"]

    # Partial / keyword match
    choice_clean = choice.lower().replace("-", " ").replace("_", " ")
    for t in tracks:
        if choice_clean in t["name"].lower() or choice_clean in t["filename"].lower():
            return t["path"]

    # If user passed a direct valid file path
    p = Path(choice)
    if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS:
        return str(p.resolve())

    logger.warning(f"[BgMusic] Requested track not found: '{choice}'. Available: {[t['filename'] for t in tracks]}")
    return None


def list_available_tracks() -> List[Dict[str, Any]]:
    """Returns all available background music tracks formatted for UI/API consumption."""
    tracks = scan_music_directories()
    return [
        {
            "id": t["filename"],
            "name": t["name"],
            "duration_s": round(t["duration_s"], 1),
            "moods": t["moods"],
            "tags": t["tags"],
            "path": t["path"]
        }
        for t in tracks
    ]
