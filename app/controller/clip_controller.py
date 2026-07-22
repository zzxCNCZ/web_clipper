import asyncio
import logging
import secrets
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from starlette.datastructures import UploadFile

from app.extensions import limiter
from app.schemas import ClipResponse, HealthResponse
from app.utils.auth import verify_token

logger = logging.getLogger(__name__)
router = APIRouter(tags=["clips"])


@router.get("/health", response_model=HealthResponse, tags=["system"])
async def health(request: Request) -> HealthResponse:
    settings = request.app.state.settings
    configured = bool(settings.api_key) and not settings.missing_integration_settings()
    return HealthResponse(status="ok", configured=configured)


@router.post("/upload", response_model=ClipResponse)
@router.post("/upload/", response_model=ClipResponse, include_in_schema=False)
@limiter.limit("10/minute")
async def upload_file(
    request: Request,
    _token: str = Depends(verify_token),
) -> ClipResponse:
    request_started_at = time.perf_counter()
    clip_id = secrets.token_hex(8)
    settings = request.app.state.settings
    form = await request.form()
    original_url = str(form.get("url", "")).strip()
    upload = next((value for value in form.values() if isinstance(value, UploadFile)), None)
    if upload is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file content found in form data",
        )

    raw_filename = upload.filename or "clip.html"
    filename = raw_filename.replace("\\", "/").rsplit("/", 1)[-1] or "clip.html"
    extension = Path(filename).suffix.lower()
    if not extension:
        filename += ".html"
    elif extension not in settings.allowed_extensions:
        allowed = ", ".join(sorted(settings.allowed_extensions))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed. Allowed types: {allowed}",
        )

    content = await upload.read()
    await upload.close()
    if len(content) > settings.max_file_size:
        max_size_mb = settings.max_file_size / 1024 / 1024
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size allowed: {max_size_mb:g}MB",
        )

    logger.info(
        "[%s] upload status=received filename=%s size_bytes=%d source_url_provided=%s client=%s",
        clip_id,
        filename,
        len(content),
        bool(original_url),
        request.client.host if request.client else "unknown",
    )
    file_path = settings.upload_dir / f"{clip_id}_{filename}"
    await asyncio.to_thread(file_path.write_bytes, content)
    try:
        result = await request.app.state.clipper.process_file(file_path, original_url)
        logger.info(
            "[%s] upload status=completed elapsed=%.3fs",
            clip_id,
            time.perf_counter() - request_started_at,
        )
        return ClipResponse.model_validate(result)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "[%s] upload status=failed filename=%s elapsed=%.3fs",
            clip_id,
            filename,
            time.perf_counter() - request_started_at,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    finally:
        await asyncio.to_thread(file_path.unlink, missing_ok=True)
        logger.debug("[%s] temporary upload removed path=%s", clip_id, file_path)
