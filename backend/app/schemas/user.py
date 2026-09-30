from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UserBase(BaseModel):
    username: str = Field(min_length=2, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    nickname: str = Field(default="", max_length=100)
    status: str = Field(default="ENABLED", pattern=r"^(ENABLED|DISABLED)$")


class UserCreate(UserBase):
    password: str = Field(min_length=6, max_length=128)


class UserUpdate(BaseModel):
    nickname: str | None = Field(default=None, max_length=100)
    status: str | None = Field(default=None, pattern=r"^(ENABLED|DISABLED)$")


class PasswordChange(BaseModel):
    password: str = Field(min_length=6, max_length=128)


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    last_login_time: datetime | None
    created_at: datetime
    updated_at: datetime

