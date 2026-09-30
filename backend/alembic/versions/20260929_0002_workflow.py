"""Create workflow management tables.

Revision ID: 20260929_0002
Revises: 20260929_0001
Create Date: 2026-09-29
"""

from alembic import op
import sqlalchemy as sa


revision = "20260929_0002"
down_revision = "20260929_0001"
branch_labels = None
depends_on = None


def _timestamp_columns() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def upgrade() -> None:
    op.create_table(
        "ai_model_config",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("model_type", sa.String(20), nullable=False),
        sa.Column("provider", sa.String(60), nullable=False),
        sa.Column("base_url", sa.String(500), nullable=True),
        sa.Column("model_name", sa.String(150), nullable=False),
        sa.Column("api_key_env", sa.String(100), nullable=True),
        sa.Column("extra_config", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        *_timestamp_columns(),
        sa.ForeignKeyConstraint(["created_by"], ["sys_user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("name", "model_type", "status", "created_by"):
        op.create_index(f"ix_ai_model_config_{column}", "ai_model_config", [column])

    op.create_table(
        "ai_prompt",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.BigInteger(), nullable=True),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("prompt_type", sa.String(30), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("negative_prompt", sa.Text(), nullable=True),
        sa.Column("variables", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        *_timestamp_columns(),
        sa.ForeignKeyConstraint(["project_id"], ["ai_project.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["sys_user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("project_id", "name", "prompt_type", "status", "created_by"):
        op.create_index(f"ix_ai_prompt_{column}", "ai_prompt", [column])

    for table, detail_columns in (
        (
            "ai_character",
            (
                sa.Column("description", sa.Text(), nullable=True),
                sa.Column("appearance", sa.Text(), nullable=True),
                sa.Column("personality", sa.Text(), nullable=True),
            ),
        ),
        (
            "ai_scene",
            (
                sa.Column("description", sa.Text(), nullable=True),
                sa.Column("environment", sa.Text(), nullable=True),
                sa.Column("atmosphere", sa.Text(), nullable=True),
            ),
        ),
    ):
        op.create_table(
            table,
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("project_id", sa.BigInteger(), nullable=False),
            sa.Column("name", sa.String(150), nullable=False),
            *detail_columns,
            sa.Column("reference_file_id", sa.BigInteger(), nullable=True),
            sa.Column("prompt_id", sa.BigInteger(), nullable=True),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("created_by", sa.BigInteger(), nullable=False),
            *_timestamp_columns(),
            sa.ForeignKeyConstraint(["project_id"], ["ai_project.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["reference_file_id"], ["ai_file.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["prompt_id"], ["ai_prompt.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["created_by"], ["sys_user.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
        )
        for column in ("project_id", "name", "status", "created_by"):
            op.create_index(f"ix_{table}_{column}", table, [column])

    op.create_table(
        "ai_script",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("duration", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        *_timestamp_columns(),
        sa.ForeignKeyConstraint(["project_id"], ["ai_project.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["sys_user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("project_id", "title", "status", "created_by"):
        op.create_index(f"ix_ai_script_{column}", "ai_script", [column])

    op.create_table(
        "ai_storyboard",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("script_id", sa.BigInteger(), nullable=False),
        sa.Column("project_id", sa.BigInteger(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("duration", sa.Float(), nullable=True),
        sa.Column("camera", sa.String(200), nullable=True),
        sa.Column("dialogue", sa.Text(), nullable=True),
        sa.Column("video_prompt", sa.Text(), nullable=True),
        sa.Column("scene_id", sa.BigInteger(), nullable=True),
        sa.Column("character_ids", sa.JSON(), nullable=False),
        sa.Column("reference_file_ids", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        *_timestamp_columns(),
        sa.ForeignKeyConstraint(["script_id"], ["ai_script.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["ai_project.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scene_id"], ["ai_scene.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["sys_user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("script_id", "project_id", "status", "created_by"):
        op.create_index(f"ix_ai_storyboard_{column}", "ai_storyboard", [column])

    op.create_table(
        "ai_task",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("project_id", sa.BigInteger(), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("task_type", sa.String(30), nullable=False),
        sa.Column("target_type", sa.String(30), nullable=True),
        sa.Column("target_id", sa.BigInteger(), nullable=True),
        sa.Column("model_config_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=False),
        sa.Column("result_payload", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        *_timestamp_columns(),
        sa.ForeignKeyConstraint(["project_id"], ["ai_project.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["model_config_id"], ["ai_model_config.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["sys_user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("project_id", "name", "task_type", "status", "created_by"):
        op.create_index(f"ix_ai_task_{column}", "ai_task", [column])


def downgrade() -> None:
    op.drop_table("ai_task")
    op.drop_table("ai_storyboard")
    op.drop_table("ai_script")
    op.drop_table("ai_scene")
    op.drop_table("ai_character")
    op.drop_table("ai_prompt")
    op.drop_table("ai_model_config")
