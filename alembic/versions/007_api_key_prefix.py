"""Add merchant API key prefix column for faster lookups

Revision ID: 007
Revises: 006
Create Date: 2026-07-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("merchants", sa.Column("key_prefix", sa.String(length=16), nullable=True))
    op.create_index(op.f("ix_merchants_key_prefix"), "merchants", ["key_prefix"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_merchants_key_prefix"), table_name="merchants")
    op.drop_column("merchants", "key_prefix")
