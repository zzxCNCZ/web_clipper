from pathlib import Path
import secrets
from fastapi import HTTPException, UploadFile

ALLOWED_EXTENSIONS = {'.html', '.htm'}
MAX_FILE_SIZE = 10 * 1024 * 1024
UPLOAD_DIR = Path("uploads")

UPLOAD_DIR.mkdir(exist_ok=True)

def verify_file(file: UploadFile):
    """Verify uploaded file"""
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    file.file.seek(0, 2)  # Move to end of file
    size = file.file.tell()  # Get file size
    file.file.seek(0)  # Reset file pointer

    if size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size allowed: {MAX_FILE_SIZE/1024/1024}MB"
        )

    return file
