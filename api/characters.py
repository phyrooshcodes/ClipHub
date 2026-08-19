import logging
from typing import Optional
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from modules.character_manager import (
    delete_character,
    list_characters,
    save_character,
)

logger = logging.getLogger("ClipHub.API.Characters")
router = APIRouter(prefix="/api/characters", tags=["characters"])


@router.get("")
async def get_characters():
    """
    Returns list of all available characters (built-in and custom uploaded).
    """
    try:
        chars = list_characters()
        return {"characters": chars}
    except Exception as e:
        logger.error(f"[API] Failed to list characters: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload")
async def upload_character(
    file: UploadFile = File(...),
    name: Optional[str] = Form(None)
):
    """
    Uploads a new character image cutout (.png, .jpg, .jpeg, .webp) and saves it to avatars library.
    """
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="No filename provided.")
        
        # Read file contents
        content = await file.read()
        if not content or len(content) < 100:
            raise HTTPException(status_code=400, detail="Uploaded file is empty or corrupted.")
            
        char_info = save_character(
            file_bytes=content,
            original_filename=file.filename,
            display_name=name or ""
        )
        return {"success": True, "character": char_info}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"[API] Character upload failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to upload character: {str(e)}")


@router.delete("/{character_id}")
async def delete_custom_character(character_id: str):
    """
    Deletes a user-uploaded character from the avatars library.
    """
    try:
        delete_character(character_id)
        return {"success": True, "message": f"Character {character_id} deleted."}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"[API] Character deletion failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete character: {str(e)}")
