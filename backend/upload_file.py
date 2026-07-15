from fastapi import UploadFile, HTTPException, status
import os
import uuid
from datetime import datetime
from pathlib import Path

UPLOAD_DIRECTORY = Path("uploads")
ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/gif", "image/webp"]
ALLOWED_VIDEO_TYPES = ["video/mp4", "video/mpeg", "video/ogg"]
ALLOWED_AUDIO_TYPES = ["audio/mpeg", "audio/wav", "audio/ogg"]
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB

# Create upload directory if it doesn't exist
UPLOAD_DIRECTORY.mkdir(exist_ok=True)

async def handle_file_upload(file: UploadFile, user_id: int):
    # Validate file size
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large"
        )
    
    # Validate file type
    mime_type = file.content_type
    file_type = get_file_type(mime_type)
    
    if not file_type:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported file type"
        )
    
    # Generate unique filename
    file_extension = Path(file.filename).suffix
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    
    # Create user-specific directory
    user_dir = UPLOAD_DIRECTORY / str(user_id)
    user_dir.mkdir(exist_ok=True)
    
    file_path = user_dir / unique_filename
    
    # Save file
    with open(file_path, "wb") as f:
        f.write(contents)
    
    return {
        "file_url": f"/uploads/{user_id}/{unique_filename}",
        "file_name": file.filename,
        "file_size": len(contents),
        "mime_type": mime_type,
        "file_type": file_type
    }

def get_file_type(mime_type: str) -> str:
    if not mime_type:
        return "file"
    if mime_type in ALLOWED_IMAGE_TYPES:
        return "image"
    elif mime_type in ALLOWED_VIDEO_TYPES:
        return "video"
    elif mime_type in ALLOWED_AUDIO_TYPES:
        return "audio"
    elif mime_type.startswith("audio/"):
        return "audio"
    else:
        return "file"
