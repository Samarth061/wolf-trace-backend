"""
File Upload Router

Handles media file uploads for forensic analysis.
Files are saved temporarily and their URLs are returned for evidence creation.
"""

from fastapi import APIRouter, UploadFile, File, HTTPException
from typing import Dict
import os
import shutil
from pathlib import Path
import uuid

router = APIRouter(prefix="/api", tags=["files"])

# Create uploads directory if it doesn't exist
UPLOAD_DIR = Path("/tmp/wolftrace-uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)) -> Dict[str, str]:
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

        # Return file URL (using file:// protocol for local files)
        file_url = f"file://{file_path}"

        return {
            "url": file_url,
            "filename": file.filename or unique_filename,
            "content_type": file.content_type,
            "size": file_path.stat().st_size
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")


@router.delete("/upload/{filename}")
async def delete_file(filename: str) -> Dict[str, str]:
    """
    Delete an uploaded file.

    Args:
        filename: Name of the file to delete

    Returns:
        Success message
    """
    file_path = UPLOAD_DIR / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    try:
        file_path.unlink()
        return {"status": "deleted", "filename": filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File deletion failed: {str(e)}")
