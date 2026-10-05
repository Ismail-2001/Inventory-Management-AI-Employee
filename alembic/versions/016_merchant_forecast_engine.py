"""Merchant-level forecast engine selection (promotion flag).

Revision ID: 016
Revises: 015
Create Date: 2026-10-04
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "016"
down_revision: str | None = "015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "merchants",
        sa.Column(
            "forecast_engine",
            sa.String(length=16),
            nullable=False,
            server_default="shadow",
        ),
    )
    op.add_column(
        "merchants",
        sa.Column("forecast_promoted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("UPDATE merchants SET forecast_engine = 'shadow'")


def downgrade() -> None:
    op.drop_column("merchants", "forecast_promoted_at")
    op.drop_column("merchants", "forecast_engine")
