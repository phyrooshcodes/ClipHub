import logging
from typing import Optional
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from modules.cover_manager import (
    delete_cover,
    list_covers,
    save_cover,
)

logger = logging.getLogger("ClipHub.API.Covers")
router = APIRouter(prefix="/api/covers", tags=["covers"])


@router.get("")
async def get_covers():
    """
    Returns list of all available universal thumbnail options.
    """
    try:
        covers = list_covers()
        return {"covers": covers}
    except Exception as e:
        logger.error(f"[API] Failed to list covers: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload")
async def upload_cover(
    file: UploadFile = File(...),
    name: Optional[str] = Form(None)
):
    """
    Uploads a new universal thumbnail image (.jpg, .jpeg, .png, .webp) and saves it to covers library.
    """
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="No filename provided.")

        content = await file.read()
        if not content or len(content) < 100:
            raise HTTPException(status_code=400, detail="Uploaded file is empty or corrupted.")

        cover_info = save_cover(
            file_bytes=content,
            original_filename=file.filename,
            display_name=name or ""
        )
        return {"success": True, "cover": cover_info}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"[API] Cover upload failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to upload cover: {str(e)}")


@router.delete("/{cover_id}")
async def delete_custom_cover(cover_id: str):
    """
    Deletes a user-uploaded universal cover thumbnail.
    """
    try:
        delete_cover(cover_id)
        return {"success": True, "message": f"Cover {cover_id} deleted."}
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"[API] Cover deletion failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete cover: {str(e)}")
