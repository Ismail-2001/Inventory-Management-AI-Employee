"""Ensemble becomes the default primary forecast engine.

Revision ID: 018
Revises: 017
Create Date: 2026-10-05
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "018"
down_revision: str | None = "017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "merchants",
        "forecast_engine",
        existing_type=sa.String(length=16),
        nullable=False,
        server_default="ensemble",
    )
    op.execute("UPDATE merchants SET forecast_engine = 'ensemble' WHERE forecast_engine = 'shadow'")


def downgrade() -> None:
    op.alter_column(
        "merchants",
        "forecast_engine",
        existing_type=sa.String(length=16),
        nullable=False,
        server_default="shadow",
    )
    op.execute("UPDATE merchants SET forecast_engine = 'shadow' WHERE forecast_engine = 'ensemble'")
