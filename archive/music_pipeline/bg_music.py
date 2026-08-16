import os
import urllib.request
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

MUSIC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Music"))
os.makedirs(MUSIC_DIR, exist_ok=True)

CURATED_TRACKS = {
    "ambient": {
        "name": "Inspiring Ambient (Soft Piano & Pads)",
        "url": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-8.mp3",
        "filename": "inspiring_ambient.mp3"
    },
    "lofi": {
        "name": "Chill Lofi Beat (Conversational/Cozy)",
        "url": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-3.mp3",
        "filename": "chill_lofi.mp3"
    },
    "focus": {
        "name": "Deep Focus Synth (Calm & Minimal)",
        "url": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",
        "filename": "deep_focus.mp3"
    }
}


def ensure_music_library_json():
    """Ensure that the music_library.json has correct tag configurations for our curated tracks."""
    manifest_path = os.path.join(MUSIC_DIR, "music_library.json")
    import json
    
    manifest = {}
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception:
            pass

    updated = False
    for key, info in CURATED_TRACKS.items():
        fname = info["filename"]
        if fname not in manifest:
            if key == "ambient":
                manifest[fname] = {
                    "name": info["name"],
                    "moods": ["warm_reflection", "calm_focus"],
                    "tags": ["ambient", "piano", "warm", "soft", "gentle"],
                    "start_offset_s": 0.0,
                    "enabled": True
                }
            elif key == "lofi":
                manifest[fname] = {
                    "name": info["name"],
                    "moods": ["calm_focus", "measured_momentum"],
                    "tags": ["lofi", "chill", "beat", "soft", "focus"],
                    "start_offset_s": 0.0,
                    "enabled": True
                }
            elif key == "focus":
                manifest[fname] = {
                    "name": info["name"],
                    "moods": ["calm_focus"],
                    "tags": ["focus", "synth", "minimal", "calm", "ambient"],
                    "start_offset_s": 0.0,
                    "enabled": True
                }
            updated = True

    if updated:
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)


def get_music_track(choice: str) -> Optional[str]:
    """
    Get the absolute path to a background music file based on choice.
    Downloads curated tracks if needed, or checks the Music/ directory.
    """
    if not choice or choice.lower() in ("none", ""):
        return None

    # Ensure metadata manifest exists for MusicDirector tag matching
    ensure_music_library_json()

    # 1. Check if it's a curated track
    if choice in CURATED_TRACKS:
        track_info = CURATED_TRACKS[choice]
        local_path = os.path.join(MUSIC_DIR, track_info["filename"])
        
        if not os.path.exists(local_path):
            logger.info(f"[BgMusic] Downloading curated track '{track_info['name']}'...")
            try:
                # Set a User-Agent to avoid generic blocks
                req = urllib.request.Request(
                    track_info["url"],
                    headers={"User-Agent": "Mozilla/5.0"}
                )
                with urllib.request.urlopen(req, timeout=30) as response:
                    with open(local_path, "wb") as f:
                        f.write(response.read())
                logger.info(f"[BgMusic] Successfully downloaded to {local_path}")
            except Exception as e:
                logger.error(f"[BgMusic] Failed to download track: {e}")
                return None
        return local_path

    # 2. Check if it's a custom file in the Music/ folder
    custom_path = os.path.join(MUSIC_DIR, choice)
    if os.path.exists(custom_path):
        return custom_path

    # Check if they passed a filename without extension
    for ext in (".mp3", ".wav", ".m4a"):
        alt_path = os.path.join(MUSIC_DIR, choice + ext)
        if os.path.exists(alt_path):
            return alt_path

    logger.warning(f"[BgMusic] Requested track not found: {choice}")
    return None


def list_available_tracks() -> List[Dict[str, str]]:
    """
    List all available tracks, including curated templates and custom
    files placed in the Music/ directory.
    """
    tracks = []
    
    # 1. Add Curated Tracks
    for key, info in CURATED_TRACKS.items():
        local_path = os.path.join(MUSIC_DIR, info["filename"])
        tracks.append({
            "id": key,
            "name": info["name"],
            "status": "cached" if os.path.exists(local_path) else "downloadable"
        })

    # 2. Add Custom files in Music/ directory
    if os.path.exists(MUSIC_DIR):
        for f in os.listdir(MUSIC_DIR):
            if f.endswith((".mp3", ".wav", ".m4a")):
                # Avoid listing the downloaded names as duplicates
                if f not in [info["filename"] for info in CURATED_TRACKS.values()]:
                    tracks.append({
                        "id": f,
                        "name": f"Custom: {f}",
                        "status": "cached"
                    })
                    
    return tracks
