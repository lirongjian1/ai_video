from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.dependencies import CurrentUser, DbSession
from app.core.security import create_access_token, verify_password
from app.models.user import SysUser
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.common import MessageResponse
from app.schemas.user import UserRead


router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: DbSession) -> TokenResponse:
    user = db.scalar(select(SysUser).where(SysUser.username == payload.username))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    if user.status != "ENABLED":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被禁用")
    user.last_login_time = datetime.now()
    db.commit()
    db.refresh(user)
    token = create_access_token(str(user.id), {"username": user.username})
    return TokenResponse(access_token=token, user=UserRead.model_validate(user))


@router.get("/me", response_model=UserRead)
def me(current_user: CurrentUser) -> SysUser:
    return current_user


@router.post("/logout", response_model=MessageResponse)
def logout(_: CurrentUser) -> MessageResponse:
    return MessageResponse(message="已退出登录")

