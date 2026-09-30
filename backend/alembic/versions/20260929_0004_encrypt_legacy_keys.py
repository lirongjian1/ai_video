"""Encrypt legacy API keys saved in the environment-name field.

Revision ID: 20260929_0004
Revises: 20260929_0003
Create Date: 2026-09-29
"""

import re

from alembic import op
import sqlalchemy as sa

from app.services.secret_store import encrypt_secret


revision = "20260929_0004"
down_revision = "20260929_0003"
branch_labels = None
depends_on = None


ENV_NAME = re.compile(r"^[A-Z_][A-Z0-9_]{1,99}$")


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT id, api_key_env FROM ai_model_config "
            "WHERE api_key_encrypted IS NULL AND api_key_env IS NOT NULL"
        )
    ).mappings()
    for row in rows:
        value = str(row["api_key_env"]).strip()
        if value and not ENV_NAME.fullmatch(value):
            connection.execute(
                sa.text(
                    "UPDATE ai_model_config "
                    "SET api_key_encrypted = :encrypted, api_key_env = NULL WHERE id = :id"
                ),
                {"encrypted": encrypt_secret(value), "id": row["id"]},
            )


def downgrade() -> None:
    pass
