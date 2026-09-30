from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class SysUser(TimestampMixin, Base):
    __tablename__ = "sys_user"
    __table_args__ = (
        UniqueConstraint("username", name="uq_sys_user_username"),
        Index("ix_sys_user_username", "username"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    nickname: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ENABLED", index=True)
    last_login_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

