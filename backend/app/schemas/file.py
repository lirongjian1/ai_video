from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int | None
    file_name: str
    original_name: str
    file_type: str
    mime_type: str
    file_size: int
    storage_type: str
    storage_path: str
    url: str
    thumbnail_url: str | None
    width: int | None
    height: int | None
    duration: float | None
    source_type: str
    source_id: int | None
    created_by: int
    created_at: datetime
    updated_at: datetime


class FileRename(BaseModel):
    file_name: str = Field(min_length=1, max_length=255)

