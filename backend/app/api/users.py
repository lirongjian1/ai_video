from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, or_, select

from app.api.dependencies import CurrentUser, DbSession
from app.core.security import hash_password
from app.models.user import SysUser
from app.schemas.common import MessageResponse, Page
from app.schemas.user import PasswordChange, UserCreate, UserRead, UserUpdate


router = APIRouter(prefix="/users", tags=["用户管理"])


@router.get("", response_model=Page[UserRead])
def list_users(
    _: CurrentUser,
    db: DbSession,
    keyword: str | None = Query(default=None, max_length=100),
    status_filter: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> Page[UserRead]:
    filters = []
    if keyword:
        pattern = f"%{keyword.strip()}%"
        filters.append(or_(SysUser.username.like(pattern), SysUser.nickname.like(pattern)))
    if status_filter:
        filters.append(SysUser.status == status_filter)
    total = db.scalar(select(func.count(SysUser.id)).where(*filters)) or 0
    users = db.scalars(
        select(SysUser)
        .where(*filters)
        .order_by(SysUser.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page(items=list(users), total=total, page=page, page_size=page_size)


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, _: CurrentUser, db: DbSession) -> SysUser:
    if db.scalar(select(SysUser.id).where(SysUser.username == payload.username)):
        raise HTTPException(status_code=409, detail="用户名已存在")
    user = SysUser(
        username=payload.username,
        password_hash=hash_password(payload.password),
        nickname=payload.nickname,
        status=payload.status,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.put("/{user_id}", response_model=UserRead)
def update_user(user_id: int, payload: UserUpdate, _: CurrentUser, db: DbSession) -> SysUser:
    user = db.get(SysUser, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user


@router.put("/{user_id}/password", response_model=MessageResponse)
def change_password(
    user_id: int, payload: PasswordChange, _: CurrentUser, db: DbSession
) -> MessageResponse:
    user = db.get(SysUser, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.password_hash = hash_password(payload.password)
    db.commit()
    return MessageResponse(message="密码修改成功")


@router.delete("/{user_id}", response_model=MessageResponse)
def delete_user(user_id: int, current_user: CurrentUser, db: DbSession) -> MessageResponse:
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="不能删除当前登录用户")
    user = db.get(SysUser, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    db.delete(user)
    db.commit()
    return MessageResponse(message="用户已删除")

