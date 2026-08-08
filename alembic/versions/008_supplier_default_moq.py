"""Add a default MOQ field for suppliers

Revision ID: 008
Revises: 007
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "008"
down_revision: str | None = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("suppliers", sa.Column("default_moq", sa.Integer(), nullable=False, server_default="1"))


def downgrade() -> None:
    op.drop_column("suppliers", "default_moq")
