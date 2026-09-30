from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select

from app.api.dependencies import CurrentUser, DbSession
from app.models.file import AiFile
from app.models.project import AiProject
from app.schemas.common import MessageResponse, Page
from app.schemas.file import FileRead, FileRename
from app.services.file_storage import classify_file, resolve_storage_file, save_upload


router = APIRouter(prefix="/files", tags=["文件管理"])


@router.get("", response_model=Page[FileRead])
def list_files(
    _: CurrentUser,
    db: DbSession,
    keyword: str | None = Query(default=None, max_length=255),
    project_id: int | None = None,
    file_type: str | None = None,
    source_type: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Page[FileRead]:
    filters = []
    if keyword:
        pattern = f"%{keyword.strip()}%"
        filters.append(or_(AiFile.file_name.like(pattern), AiFile.original_name.like(pattern)))
    if project_id is not None:
        filters.append(AiFile.project_id == project_id)
    if file_type:
        filters.append(AiFile.file_type == file_type)
    if source_type:
        filters.append(AiFile.source_type == source_type)
    total = db.scalar(select(func.count(AiFile.id)).where(*filters)) or 0
    files = db.scalars(
        select(AiFile)
        .where(*filters)
        .order_by(AiFile.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page(items=list(files), total=total, page=page, page_size=page_size)


@router.post("/upload", response_model=FileRead, status_code=status.HTTP_201_CREATED)
async def upload_file(
    current_user: CurrentUser,
    db: DbSession,
    upload: UploadFile = File(...),
    project_id: int | None = Form(default=None),
) -> AiFile:
    if project_id is not None and db.get(AiProject, project_id) is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    file_type = classify_file(upload.content_type)
    _, relative_path, file_size = await save_upload(upload, project_id)
    original_name = Path(upload.filename or "未命名文件").name
    record = AiFile(
        project_id=project_id,
        file_name=original_name,
        original_name=original_name,
        file_type=file_type,
        mime_type=upload.content_type or "application/octet-stream",
        file_size=file_size,
        storage_type="LOCAL",
        storage_path=relative_path,
        url=f"/storage/{relative_path}",
        source_type="UPLOAD",
        created_by=current_user.id,
    )
    db.add(record)
    try:
        db.commit()
    except Exception:
        resolve_storage_file(relative_path).unlink(missing_ok=True)
        raise
    db.refresh(record)
    return record


@router.put("/{file_id}", response_model=FileRead)
def rename_file(
    file_id: int, payload: FileRename, _: CurrentUser, db: DbSession
) -> AiFile:
    record = db.get(AiFile, file_id)
    if record is None:
        raise HTTPException(status_code=404, detail="文件不存在")
    record.file_name = Path(payload.file_name).name
    db.commit()
    db.refresh(record)
    return record


@router.get("/{file_id}/download")
def download_file(file_id: int, _: CurrentUser, db: DbSession) -> FileResponse:
    record = db.get(AiFile, file_id)
    if record is None:
        raise HTTPException(status_code=404, detail="文件不存在")
    path = resolve_storage_file(record.storage_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="磁盘文件不存在")
    return FileResponse(path, media_type=record.mime_type, filename=record.file_name)


@router.delete("/{file_id}", response_model=MessageResponse)
def delete_file(file_id: int, _: CurrentUser, db: DbSession) -> MessageResponse:
    record = db.get(AiFile, file_id)
    if record is None:
        raise HTTPException(status_code=404, detail="文件不存在")
    path = resolve_storage_file(record.storage_path)
    db.delete(record)
    db.commit()
    path.unlink(missing_ok=True)
    return MessageResponse(message="文件已删除")

