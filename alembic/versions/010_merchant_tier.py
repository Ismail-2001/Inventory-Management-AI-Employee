"""Add merchant tier column for plan-based feature gating

Revision ID: 010
Revises: 009
Create Date: 2026-08-05
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "010"
down_revision: str | None = "009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("merchants", sa.Column("tier", sa.String(length=16), server_default="developer", nullable=False))


def downgrade() -> None:
    op.drop_column("merchants", "tier")
