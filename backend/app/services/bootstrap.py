from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.user import SysUser


def ensure_default_admin(db: Session) -> None:
    existing = db.scalar(select(SysUser).where(SysUser.username == "admin"))
    if existing is not None:
        return
    db.add(
        SysUser(
            username="admin",
            password_hash=hash_password("admin123"),
            nickname="系统管理员",
            status="ENABLED",
        )
    )
    db.commit()

