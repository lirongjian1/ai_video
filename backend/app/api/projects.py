from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, or_, select

from app.api.dependencies import CurrentUser, DbSession
from app.models.project import AiProject
from app.schemas.common import MessageResponse, Page
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate


router = APIRouter(prefix="/projects", tags=["项目管理"])


@router.get("", response_model=Page[ProjectRead])
def list_projects(
    _: CurrentUser,
    db: DbSession,
    keyword: str | None = Query(default=None, max_length=150),
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Page[ProjectRead]:
    filters = []
    if keyword:
        pattern = f"%{keyword.strip()}%"
        filters.append(or_(AiProject.name.like(pattern), AiProject.description.like(pattern)))
    if status_filter:
        filters.append(AiProject.status == status_filter)
    total = db.scalar(select(func.count(AiProject.id)).where(*filters)) or 0
    projects = db.scalars(
        select(AiProject)
        .where(*filters)
        .order_by(AiProject.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page(items=list(projects), total=total, page=page, page_size=page_size)


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate, current_user: CurrentUser, db: DbSession
) -> AiProject:
    project = AiProject(**payload.model_dump(), created_by=current_user.id)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: int, _: CurrentUser, db: DbSession) -> AiProject:
    project = db.get(AiProject, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


@router.put("/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: int, payload: ProjectUpdate, _: CurrentUser, db: DbSession
) -> AiProject:
    project = db.get(AiProject, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", response_model=MessageResponse)
def delete_project(project_id: int, _: CurrentUser, db: DbSession) -> MessageResponse:
    project = db.get(AiProject, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    db.delete(project)
    db.commit()
    return MessageResponse(message="项目已删除")

