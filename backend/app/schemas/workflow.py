from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ModelConfigBase(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    model_type: str = Field(pattern=r"^(TEXT|IMAGE|VIDEO)$")
    provider: str = Field(min_length=1, max_length=60)
    base_url: str | None = Field(default=None, max_length=500)
    model_name: str = Field(min_length=1, max_length=150)
    extra_config: dict[str, Any] = Field(default_factory=dict)
    status: str = Field(default="ENABLED", pattern=r"^(ENABLED|DISABLED)$")
    is_default: bool = False

    @field_validator("model_name")
    @classmethod
    def model_name_must_be_identifier(cls, value: str) -> str:
        normalized = value.strip()
        if normalized.lower().startswith(("http://", "https://")):
            raise ValueError("模型名称应填写模型 ID，不能填写接口地址")
        return normalized


class ModelConfigCreate(ModelConfigBase):
    api_key: str | None = Field(default=None, max_length=500)
    api_key_env: str | None = Field(default=None, max_length=100)


class ModelConfigUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    model_type: str | None = Field(default=None, pattern=r"^(TEXT|IMAGE|VIDEO)$")
    provider: str | None = Field(default=None, min_length=1, max_length=60)
    base_url: str | None = Field(default=None, max_length=500)
    model_name: str | None = Field(default=None, min_length=1, max_length=150)
    api_key: str | None = Field(default=None, max_length=500)
    api_key_env: str | None = Field(default=None, max_length=100)
    extra_config: dict[str, Any] | None = None
    status: str | None = Field(default=None, pattern=r"^(ENABLED|DISABLED)$")
    is_default: bool | None = None

    @field_validator("model_name")
    @classmethod
    def model_name_must_be_identifier(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if normalized.lower().startswith(("http://", "https://")):
            raise ValueError("模型名称应填写模型 ID，不能填写接口地址")
        return normalized


class ModelConfigRead(ModelConfigBase, OrmModel):
    id: int
    has_api_key: bool
    api_key_masked: str | None
    created_by: int
    created_at: datetime
    updated_at: datetime


class PromptBase(BaseModel):
    project_id: int | None = None
    name: str = Field(min_length=1, max_length=150)
    prompt_type: str = Field(pattern=r"^(CHARACTER|SCENE|SCRIPT|STORYBOARD|VIDEO|CUSTOM)$")
    content: str = Field(min_length=1)
    negative_prompt: str | None = None
    variables: dict[str, Any] = Field(default_factory=dict)
    status: str = Field(default="ENABLED", pattern=r"^(ENABLED|DISABLED)$")


class PromptCreate(PromptBase):
    pass


class PromptUpdate(BaseModel):
    project_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=150)
    prompt_type: str | None = Field(
        default=None, pattern=r"^(CHARACTER|SCENE|SCRIPT|STORYBOARD|VIDEO|CUSTOM)$"
    )
    content: str | None = Field(default=None, min_length=1)
    negative_prompt: str | None = None
    variables: dict[str, Any] | None = None
    status: str | None = Field(default=None, pattern=r"^(ENABLED|DISABLED)$")


class PromptRead(PromptBase, OrmModel):
    id: int
    created_by: int
    created_at: datetime
    updated_at: datetime


class CharacterBase(BaseModel):
    project_id: int
    name: str = Field(min_length=1, max_length=150)
    description: str | None = None
    appearance: str | None = None
    personality: str | None = None
    reference_file_id: int | None = None
    prompt_id: int | None = None
    status: str = Field(default="ACTIVE", pattern=r"^(ACTIVE|DISABLED)$")


class CharacterCreate(CharacterBase):
    pass


class CharacterUpdate(BaseModel):
    project_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = None
    appearance: str | None = None
    personality: str | None = None
    reference_file_id: int | None = None
    prompt_id: int | None = None
    status: str | None = Field(default=None, pattern=r"^(ACTIVE|DISABLED)$")


class CharacterRead(CharacterBase, OrmModel):
    id: int
    created_by: int
    created_at: datetime
    updated_at: datetime


class SceneBase(BaseModel):
    project_id: int
    name: str = Field(min_length=1, max_length=150)
    description: str | None = None
    environment: str | None = None
    atmosphere: str | None = None
    reference_file_id: int | None = None
    prompt_id: int | None = None
    status: str = Field(default="ACTIVE", pattern=r"^(ACTIVE|DISABLED)$")


class SceneCreate(SceneBase):
    pass


class SceneUpdate(BaseModel):
    project_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = None
    environment: str | None = None
    atmosphere: str | None = None
    reference_file_id: int | None = None
    prompt_id: int | None = None
    status: str | None = Field(default=None, pattern=r"^(ACTIVE|DISABLED)$")


class SceneRead(SceneBase, OrmModel):
    id: int
    created_by: int
    created_at: datetime
    updated_at: datetime


class ScriptBase(BaseModel):
    project_id: int
    title: str = Field(min_length=1, max_length=200)
    summary: str | None = None
    content: str = ""
    duration: int | None = Field(default=None, ge=1)
    status: str = Field(default="DRAFT", pattern=r"^(DRAFT|READY|ARCHIVED)$")


class ScriptCreate(ScriptBase):
    pass


class ScriptUpdate(BaseModel):
    project_id: int | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    summary: str | None = None
    content: str | None = None
    duration: int | None = Field(default=None, ge=1)
    status: str | None = Field(default=None, pattern=r"^(DRAFT|READY|ARCHIVED)$")


class ScriptRead(ScriptBase, OrmModel):
    id: int
    storyboard_count: int = 0
    created_by: int
    created_at: datetime
    updated_at: datetime


class StoryboardBase(BaseModel):
    script_id: int
    sequence: int = Field(default=1, ge=1)
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    duration: float | None = Field(default=None, gt=0)
    camera: str | None = Field(default=None, max_length=200)
    dialogue: str | None = None
    video_prompt: str | None = None
    scene_id: int | None = None
    character_ids: list[int] = Field(default_factory=list)
    reference_file_ids: list[int] = Field(default_factory=list)
    status: str = Field(default="DRAFT", pattern=r"^(DRAFT|READY|GENERATED)$")


class StoryboardCreate(StoryboardBase):
    pass


class StoryboardUpdate(BaseModel):
    sequence: int | None = Field(default=None, ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    duration: float | None = Field(default=None, gt=0)
    camera: str | None = Field(default=None, max_length=200)
    dialogue: str | None = None
    video_prompt: str | None = None
    scene_id: int | None = None
    character_ids: list[int] | None = None
    reference_file_ids: list[int] | None = None
    status: str | None = Field(default=None, pattern=r"^(DRAFT|READY|GENERATED)$")


class StoryboardRead(StoryboardBase, OrmModel):
    id: int
    project_id: int
    created_by: int
    created_at: datetime
    updated_at: datetime


class TaskBase(BaseModel):
    project_id: int | None = None
    name: str = Field(min_length=1, max_length=200)
    task_type: str = Field(pattern=r"^(TEXT|IMAGE|VIDEO|MERGE)$")
    target_type: str | None = Field(default=None, max_length=30)
    target_id: int | None = None
    model_config_id: int | None = None
    request_payload: dict[str, Any] = Field(default_factory=dict)


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    status: str | None = Field(
        default=None, pattern=r"^(PENDING|RUNNING|SUCCESS|FAILED|CANCELLED)$"
    )
    progress: int | None = Field(default=None, ge=0, le=100)
    result_payload: dict[str, Any] | None = None
    error_message: str | None = None


class TaskRead(TaskBase, OrmModel):
    id: int
    status: str
    progress: int
    result_payload: dict[str, Any]
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_by: int
    created_at: datetime
    updated_at: datetime


class VideoMergeCreate(BaseModel):
    project_id: int | None = None
    name: str = Field(min_length=1, max_length=200)
    output_name: str = Field(min_length=1, max_length=200)
    file_ids: list[int] = Field(min_length=2)


class TaskCapabilities(BaseModel):
    ffmpeg_available: bool


class ModelConnectionResult(BaseModel):
    ok: bool
    message: str


class PromptGenerateRequest(BaseModel):
    project_id: int | None = None
    name: str = Field(min_length=1, max_length=150)
    generation_type: str = Field(pattern=r"^(CHARACTER_THREE_VIEW|SCENE)$")
    keywords: str = Field(min_length=2, max_length=5000)
    model_config_id: int


class ScriptGenerateRequest(BaseModel):
    project_id: int
    title: str = Field(min_length=1, max_length=200)
    keywords: str = Field(min_length=2, max_length=5000)
    style: str | None = Field(default=None, max_length=500)
    model_config_id: int


class ImageGenerateRequest(BaseModel):
    project_id: int | None = None
    prompt_id: int
    name: str = Field(min_length=1, max_length=200)
    model_config_id: int
    size: str = Field(default="1024x1024", max_length=30)


class VideoGenerateRequest(BaseModel):
    model_config_id: int
    reference_file_id: int | None = None
