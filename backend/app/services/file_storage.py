from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings


ALLOWED_TYPES = {
    "image": "IMAGE",
    "video": "VIDEO",
}


def classify_file(mime_type: str | None) -> str:
    family = (mime_type or "").split("/", 1)[0].lower()
    file_type = ALLOWED_TYPES.get(family)
    if file_type is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="当前版本仅支持上传图片和视频",
        )
    return file_type


async def save_upload(upload: UploadFile, project_id: int | None) -> tuple[Path, str, int]:
    max_bytes = settings.max_upload_mb * 1024 * 1024
    suffix = Path(upload.filename or "").suffix.lower()[:20]
    now = datetime.now()
    relative_dir = Path(str(project_id or "common")) / str(now.year) / f"{now.month:02d}"
    relative_path = relative_dir / f"{uuid4().hex}{suffix}"
    absolute_path = (settings.storage_path / relative_path).resolve()
    absolute_path.parent.mkdir(parents=True, exist_ok=True)

    size = 0
    try:
        with absolute_path.open("wb") as output:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"文件不能超过 {settings.max_upload_mb} MB",
                    )
                output.write(chunk)
    except Exception:
        absolute_path.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()

    return absolute_path, relative_path.as_posix(), size


def resolve_storage_file(relative_path: str) -> Path:
    candidate = (settings.storage_path / relative_path).resolve()
    if not candidate.is_relative_to(settings.storage_path.resolve()):
        raise HTTPException(status_code=400, detail="非法文件路径")
    return candidate

