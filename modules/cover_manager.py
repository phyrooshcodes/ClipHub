import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("ClipHub.CoverManager")

COVERS_DIR = Path(__file__).resolve().parent.parent / "assets" / "covers"
META_FILE = COVERS_DIR / "covers_meta.json"

NO_COVER_OPTION = {
    "id": "none",
    "name": "No Universal Thumbnail",
    "filename": "none",
    "url": "",
    "is_builtin": True,
    "is_none": True,
    "description": "Extract dynamic thumbnail directly from video (Frame 0.0s)"
}

DEFAULT_BUILTIN_COVER = {
    "id": "default_cover.jpg",
    "name": "Master Universal Cover",
    "filename": "default_cover.jpg",
    "url": "/assets/covers/default_cover.jpg",
    "is_builtin": True,
    "is_default": True,
    "description": "Default anime teacher studio cover"
}

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def get_covers_dir() -> Path:
    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    return COVERS_DIR


def _load_meta() -> Dict[str, Dict]:
    if not META_FILE.exists():
        return {}
    try:
        with open(META_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"[CoverManager] Failed to read {META_FILE}: {e}")
        return {}


def _save_meta(meta: Dict[str, Dict]) -> None:
    try:
        with open(META_FILE, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"[CoverManager] Failed to write {META_FILE}: {e}")


def list_covers() -> List[Dict]:
    """
    Returns the complete list of available universal thumbnail options.
    Guarantees:
    1. 'none' option (No universal thumbnail / use video frame)
    2. Default universal cover (default_cover.jpg)
    3. User-uploaded custom covers
    """
    covers_dir = get_covers_dir()
    meta = _load_meta()

    covers: List[Dict] = []
    seen_ids = set()

    # 1. Always include 'No Universal Thumbnail'
    covers.append(dict(NO_COVER_OPTION))
    seen_ids.add("none")

    # 2. Built-in default cover
    default_path = covers_dir / DEFAULT_BUILTIN_COVER["filename"]
    if default_path.exists():
        default_cover = dict(DEFAULT_BUILTIN_COVER)
        if "default_cover.jpg" in meta:
            default_cover.update(meta["default_cover.jpg"])
            default_cover["is_builtin"] = True
        covers.append(default_cover)
        seen_ids.add("default_cover.jpg")

    # 3. Scan covers folder for custom image files
    for entry in sorted(covers_dir.iterdir()):
        if entry.is_file() and entry.suffix.lower() in ALLOWED_EXTENSIONS:
            cover_id = entry.name
            if cover_id in seen_ids or cover_id == "default_cover.png":
                continue

            custom_meta = meta.get(cover_id, {})
            display_name = custom_meta.get("name")
            if not display_name:
                raw_name = entry.stem.replace("_", " ").replace("-", " ")
                display_name = " ".join(word.capitalize() for word in raw_name.split())

            cover_obj = {
                "id": cover_id,
                "name": display_name,
                "filename": entry.name,
                "url": f"/assets/covers/{entry.name}",
                "is_builtin": False,
                "is_default": False,
                "is_none": False,
                "description": custom_meta.get("description", "Custom Universal Thumbnail"),
                "created_at": custom_meta.get("created_at", entry.stat().st_mtime)
            }
            covers.append(cover_obj)
            seen_ids.add(cover_id)

    return covers


def save_cover(file_bytes: bytes, original_filename: str, display_name: str = "") -> Dict:
    """
    Saves an uploaded cover image to assets/covers/ and updates metadata.
    """
    covers_dir = get_covers_dir()

    ext = Path(original_filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Invalid image format '{ext}'. Allowed formats: {', '.join(ALLOWED_EXTENSIONS)}")

    clean_display_name = (display_name or Path(original_filename).stem).strip()
    if not clean_display_name:
        clean_display_name = "Custom Cover"

    slug = re.sub(r'[^a-zA-Z0-9_-]', '_', clean_display_name.lower())[:30].strip('_')
    if not slug:
        slug = "cover"
    timestamp = int(time.time())
    safe_filename = f"cover_{slug}_{timestamp}{ext}"
    target_path = covers_dir / safe_filename

    with open(target_path, "wb") as f:
        f.write(file_bytes)

    meta = _load_meta()
    meta[safe_filename] = {
        "id": safe_filename,
        "name": clean_display_name,
        "filename": safe_filename,
        "url": f"/assets/covers/{safe_filename}",
        "is_builtin": False,
        "is_default": False,
        "is_none": False,
        "description": "User Uploaded Universal Thumbnail",
        "created_at": timestamp
    }
    _save_meta(meta)

    logger.info(f"[CoverManager] Saved new cover: '{clean_display_name}' -> {safe_filename}")
    return meta[safe_filename]


def delete_cover(cover_id: str) -> bool:
    """
    Deletes a user-uploaded cover thumbnail. Built-in defaults cannot be deleted.
    """
    if cover_id in ("none", "default_cover.jpg", "default_cover.png", DEFAULT_BUILTIN_COVER["id"]):
        raise ValueError("Cannot delete default or system cover option.")

    covers_dir = get_covers_dir()
    target_path = covers_dir / cover_id

    try:
        target_path.resolve().relative_to(covers_dir.resolve())
    except ValueError:
        raise ValueError("Invalid cover identifier.")

    if target_path.exists():
        target_path.unlink()

    meta = _load_meta()
    if cover_id in meta:
        del meta[cover_id]
        _save_meta(meta)

    logger.info(f"[CoverManager] Deleted cover: {cover_id}")
    return True


def resolve_cover_path(cover_identifier: Optional[str]) -> Optional[str]:
    """
    Resolves a cover identifier to an absolute file path.
    - Returns None if cover_identifier is 'none', 'no_cover', 'off', 'video_frame', or empty.
    - Returns absolute path to the requested cover image if it exists on disk.
    - Falls back to default_cover.jpg if default is requested or fallback needed.
    """
    if not cover_identifier:
        return None

    clean_id = cover_identifier.strip().lower()
    if clean_id in ("none", "no_cover", "off", "video_frame", "disabled"):
        return None

    covers_dir = get_covers_dir()

    # Check if direct absolute path exists
    if os.path.exists(cover_identifier):
        return os.path.abspath(cover_identifier)

    # Check inside covers directory
    candidate = covers_dir / os.path.basename(cover_identifier)
    if candidate.exists():
        return str(candidate.resolve())

    # Check by metadata display name
    meta = _load_meta()
    for fname, info in meta.items():
        if info.get("name", "").lower() == clean_id:
            p = covers_dir / fname
            if p.exists():
                return str(p.resolve())

    if clean_id in ("default", "default_cover.jpg", "auto"):
        def_path = covers_dir / "default_cover.jpg"
        if def_path.exists():
            return str(def_path.resolve())

    logger.warning(f"[CoverManager] Cover '{cover_identifier}' not found on disk.")
    return None
