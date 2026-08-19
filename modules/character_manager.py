import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("ClipHub.CharacterManager")

AVATARS_DIR = Path(__file__).resolve().parent.parent / "assets" / "avatars"
META_FILE = AVATARS_DIR / "characters_meta.json"

DEFAULT_BUILTIN_CHARACTER = {
    "id": "anime_presenter.png",
    "name": "Kai (Anime Sensei)",
    "filename": "anime_presenter.png",
    "url": "/assets/avatars/anime_presenter.png",
    "is_builtin": True,
    "is_default": True,
    "description": "Wise older sister and self-improvement tutor"
}

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def get_avatars_dir() -> Path:
    AVATARS_DIR.mkdir(parents=True, exist_ok=True)
    return AVATARS_DIR


def _load_meta() -> Dict[str, Dict]:
    if not META_FILE.exists():
        return {}
    try:
        with open(META_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"[CharacterManager] Failed to read {META_FILE}: {e}")
        return {}


def _save_meta(meta: Dict[str, Dict]) -> None:
    try:
        with open(META_FILE, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"[CharacterManager] Failed to write {META_FILE}: {e}")


def list_characters() -> List[Dict]:
    """
    Returns the complete list of available characters (avatars).
    Guarantees the default Kai built-in character is always present first.
    """
    avatars_dir = get_avatars_dir()
    meta = _load_meta()

    characters: List[Dict] = []
    seen_ids = set()

    # 1. Always ensure default built-in character
    builtin_path = avatars_dir / DEFAULT_BUILTIN_CHARACTER["filename"]
    builtin_exists = builtin_path.exists()
    
    kai_char = dict(DEFAULT_BUILTIN_CHARACTER)
    if "anime_presenter.png" in meta:
        kai_char.update(meta["anime_presenter.png"])
        kai_char["is_builtin"] = True
    
    if builtin_exists:
        characters.append(kai_char)
        seen_ids.add("anime_presenter.png")

    # 2. Scan avatars folder for other image files
    for entry in sorted(avatars_dir.iterdir()):
        if entry.is_file() and entry.suffix.lower() in ALLOWED_EXTENSIONS:
            char_id = entry.name
            if char_id in seen_ids:
                continue

            custom_meta = meta.get(char_id, {})
            display_name = custom_meta.get("name")
            if not display_name:
                raw_name = entry.stem.replace("_", " ").replace("-", " ")
                display_name = " ".join(word.capitalize() for word in raw_name.split())

            char_obj = {
                "id": char_id,
                "name": display_name,
                "filename": entry.name,
                "url": f"/assets/avatars/{entry.name}",
                "is_builtin": False,
                "is_default": False,
                "description": custom_meta.get("description", "Custom AI Presenter"),
                "created_at": custom_meta.get("created_at", entry.stat().st_mtime)
            }
            characters.append(char_obj)
            seen_ids.add(char_id)

    return characters


def save_character(file_bytes: bytes, original_filename: str, display_name: str = "") -> Dict:
    """
    Saves an uploaded character image to assets/avatars/ and updates metadata.
    """
    avatars_dir = get_avatars_dir()
    
    ext = Path(original_filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Invalid image format '{ext}'. Allowed formats: {', '.join(ALLOWED_EXTENSIONS)}")

    clean_display_name = (display_name or Path(original_filename).stem).strip()
    if not clean_display_name:
        clean_display_name = "Custom Character"

    slug = re.sub(r'[^a-zA-Z0-9_-]', '_', clean_display_name.lower())[:30].strip('_')
    if not slug:
        slug = "character"
    timestamp = int(time.time())
    safe_filename = f"{slug}_{timestamp}{ext}"
    target_path = avatars_dir / safe_filename

    with open(target_path, "wb") as f:
        f.write(file_bytes)

    meta = _load_meta()
    meta[safe_filename] = {
        "id": safe_filename,
        "name": clean_display_name,
        "filename": safe_filename,
        "url": f"/assets/avatars/{safe_filename}",
        "is_builtin": False,
        "is_default": False,
        "description": "User Uploaded Character",
        "created_at": timestamp
    }
    _save_meta(meta)

    logger.info(f"[CharacterManager] Saved new character: '{clean_display_name}' -> {safe_filename}")
    return meta[safe_filename]


def delete_character(character_id: str) -> bool:
    """
    Deletes a user-uploaded character. Built-in characters cannot be deleted.
    """
    if character_id in ("anime_presenter.png", DEFAULT_BUILTIN_CHARACTER["id"]):
        raise ValueError("Cannot delete built-in default character.")

    avatars_dir = get_avatars_dir()
    target_path = avatars_dir / character_id
    
    try:
        target_path.resolve().relative_to(avatars_dir.resolve())
    except ValueError:
        raise ValueError("Invalid character identifier.")

    if target_path.exists():
        target_path.unlink()

    meta = _load_meta()
    if character_id in meta:
        del meta[character_id]
        _save_meta(meta)

    logger.info(f"[CharacterManager] Deleted character: {character_id}")
    return True


def resolve_character_path(character_identifier: Optional[str]) -> str:
    """
    Resolves a character identifier (filename, ID, or direct path) to an absolute file path.
    Falls back safely to assets/avatars/anime_presenter.png.
    """
    avatars_dir = get_avatars_dir()
    default_path = str((avatars_dir / "anime_presenter.png").resolve())

    if not character_identifier:
        return default_path

    if os.path.exists(character_identifier):
        return os.path.abspath(character_identifier)

    clean_id = os.path.basename(character_identifier)
    candidate = avatars_dir / clean_id
    if candidate.exists():
        return str(candidate.resolve())

    meta = _load_meta()
    for fname, info in meta.items():
        if info.get("name", "").lower() == character_identifier.lower():
            p = avatars_dir / fname
            if p.exists():
                return str(p.resolve())

    logger.warning(f"[CharacterManager] Character '{character_identifier}' not found. Falling back to default: {default_path}")
    return default_path
