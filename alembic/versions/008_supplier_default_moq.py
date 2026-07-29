"""Add a default MOQ field for suppliers

Revision ID: 008
Revises: 007
Create Date: 2026-07-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("suppliers", sa.Column("default_moq", sa.Integer(), nullable=False, server_default="1"))


def downgrade() -> None:
    op.drop_column("suppliers", "default_moq")
