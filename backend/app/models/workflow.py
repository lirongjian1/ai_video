from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


id_type = BigInteger().with_variant(Integer, "sqlite")


class AiModelConfig(TimestampMixin, Base):
    __tablename__ = "ai_model_config"

    id: Mapped[int] = mapped_column(id_type, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    model_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(60), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    model_name: Mapped[str] = mapped_column(String(150), nullable=False)
    api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    api_key_env: Mapped[str | None] = mapped_column(String(100), nullable=True)
    extra_config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ENABLED", index=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[int] = mapped_column(
        id_type, ForeignKey("sys_user.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key_encrypted or self.api_key_env)

    @property
    def api_key_masked(self) -> str | None:
        return "********" if self.has_api_key else None


class AiPrompt(TimestampMixin, Base):
    __tablename__ = "ai_prompt"

    id: Mapped[int] = mapped_column(id_type, primary_key=True, autoincrement=True)
    project_id: Mapped[int | None] = mapped_column(
        id_type, ForeignKey("ai_project.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    prompt_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    negative_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    variables: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ENABLED", index=True)
    created_by: Mapped[int] = mapped_column(
        id_type, ForeignKey("sys_user.id", ondelete="RESTRICT"), nullable=False, index=True
    )


class AiCharacter(TimestampMixin, Base):
    __tablename__ = "ai_character"

    id: Mapped[int] = mapped_column(id_type, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        id_type, ForeignKey("ai_project.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    appearance: Mapped[str | None] = mapped_column(Text, nullable=True)
    personality: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_file_id: Mapped[int | None] = mapped_column(
        id_type, ForeignKey("ai_file.id", ondelete="SET NULL"), nullable=True
    )
    prompt_id: Mapped[int | None] = mapped_column(
        id_type, ForeignKey("ai_prompt.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE", index=True)
    created_by: Mapped[int] = mapped_column(
        id_type, ForeignKey("sys_user.id", ondelete="RESTRICT"), nullable=False, index=True
    )


class AiScene(TimestampMixin, Base):
    __tablename__ = "ai_scene"

    id: Mapped[int] = mapped_column(id_type, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        id_type, ForeignKey("ai_project.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    environment: Mapped[str | None] = mapped_column(Text, nullable=True)
    atmosphere: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_file_id: Mapped[int | None] = mapped_column(
        id_type, ForeignKey("ai_file.id", ondelete="SET NULL"), nullable=True
    )
    prompt_id: Mapped[int | None] = mapped_column(
        id_type, ForeignKey("ai_prompt.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE", index=True)
    created_by: Mapped[int] = mapped_column(
        id_type, ForeignKey("sys_user.id", ondelete="RESTRICT"), nullable=False, index=True
    )


class AiScript(TimestampMixin, Base):
    __tablename__ = "ai_script"

    id: Mapped[int] = mapped_column(id_type, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        id_type, ForeignKey("ai_project.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    duration: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT", index=True)
    created_by: Mapped[int] = mapped_column(
        id_type, ForeignKey("sys_user.id", ondelete="RESTRICT"), nullable=False, index=True
    )


class AiStoryboard(TimestampMixin, Base):
    __tablename__ = "ai_storyboard"

    id: Mapped[int] = mapped_column(id_type, primary_key=True, autoincrement=True)
    script_id: Mapped[int] = mapped_column(
        id_type, ForeignKey("ai_script.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[int] = mapped_column(
        id_type, ForeignKey("ai_project.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration: Mapped[float | None] = mapped_column(Float, nullable=True)
    camera: Mapped[str | None] = mapped_column(String(200), nullable=True)
    dialogue: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    scene_id: Mapped[int | None] = mapped_column(
        id_type, ForeignKey("ai_scene.id", ondelete="SET NULL"), nullable=True
    )
    character_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)
    reference_file_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT", index=True)
    created_by: Mapped[int] = mapped_column(
        id_type, ForeignKey("sys_user.id", ondelete="RESTRICT"), nullable=False, index=True
    )


class AiTask(TimestampMixin, Base):
    __tablename__ = "ai_task"

    id: Mapped[int] = mapped_column(id_type, primary_key=True, autoincrement=True)
    project_id: Mapped[int | None] = mapped_column(
        id_type, ForeignKey("ai_project.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    task_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    target_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    target_id: Mapped[int | None] = mapped_column(id_type, nullable=True)
    model_config_id: Mapped[int | None] = mapped_column(
        id_type, ForeignKey("ai_model_config.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING", index=True)
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    result_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_by: Mapped[int] = mapped_column(
        id_type, ForeignKey("sys_user.id", ondelete="RESTRICT"), nullable=False, index=True
    )
