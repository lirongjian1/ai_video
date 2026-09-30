from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProjectBase(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=5000)
    cover_file_id: int | None = None
    status: str = Field(default="ACTIVE", pattern=r"^(ACTIVE|ARCHIVED|DISABLED)$")


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=5000)
    cover_file_id: int | None = None
    status: str | None = Field(default=None, pattern=r"^(ACTIVE|ARCHIVED|DISABLED)$")


class ProjectRead(ProjectBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_by: int
    created_at: datetime
    updated_at: datetime

