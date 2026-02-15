"""
File Upload Router

Handles media file uploads for forensic analysis.
Files are saved temporarily and their URLs are returned for evidence creation.
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, Request
from typing import Dict, Any
import os
import shutil
from pathlib import Path
import uuid

from fastapi.responses import FileResponse

from app.config import settings

router = APIRouter(prefix="/api", tags=["files"])

# Create uploads directory if it doesn't exist
UPLOAD_DIR = Path("/tmp/wolftrace-uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _safe_resolve(path: Path) -> Path:
    resolved = path.resolve()
    if resolved.parent != UPLOAD_DIR.resolve():
        raise HTTPException(status_code=400, detail="Invalid filename")
    return resolved


def _build_public_url(request: Request, filename: str) -> str:
    base = settings.media_base_url.strip().rstrip("/")
    if base:
        return f"{base}/api/upload/{filename}"
    return str(request.base_url).rstrip("/") + f"/api/upload/{filename}"


@router.post("/upload")
async def upload_file(request: Request, file: UploadFile = File(...)) -> Dict[str, Any]:
    """
    Upload a media file (image, video, or audio) for forensic analysis.

    Returns:
        Dict with 'url' key containing the file path
    """
    try:
        # Validate file type
        if not file.content_type:
            raise HTTPException(status_code=400, detail="File type could not be determined")

        allowed_types = ["image/", "video/", "audio/"]
        if not any(file.content_type.startswith(t) for t in allowed_types):
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {file.content_type}. Only images, videos, and audio files are allowed."
            )

        # Generate unique filename
        file_extension = Path(file.filename or "file").suffix
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        file_path = UPLOAD_DIR / unique_filename

        # Save file
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Return public URL for external services
        public_url = _build_public_url(request, unique_filename)

        return {
            "url": public_url,
            "file_url": public_url,
            "filename": file.filename or unique_filename,
            "content_type": file.content_type,
            "size": file_path.stat().st_size
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")


@router.get("/upload/{filename}")
async def get_file(filename: str) -> FileResponse:
    """
    Serve an uploaded file over HTTP.
    """
    file_path = _safe_resolve(UPLOAD_DIR / filename)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(str(file_path))


@router.delete("/upload/{filename}")
async def delete_file(filename: str) -> Dict[str, str]:
    """
    Delete an uploaded file.

    Args:
        filename: Name of the file to delete

    Returns:
        Success message
    """
    file_path = _safe_resolve(UPLOAD_DIR / filename)

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    try:
        file_path.unlink()
        return {"status": "deleted", "filename": filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File deletion failed: {str(e)}")
