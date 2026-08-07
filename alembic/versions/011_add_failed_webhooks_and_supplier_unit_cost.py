"""Add failed_webhooks table and suppliers.unit_cost_by_sku column

Revision ID: 011
Revises: 010
Create Date: 2026-08-06
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "failed_webhooks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.String(256), nullable=True),
        sa.Column("event_type", sa.String(128), nullable=True),
        sa.Column("payload_text", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.add_column("suppliers", sa.Column("unit_cost_by_sku", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("suppliers", "unit_cost_by_sku")
    op.drop_table("failed_webhooks")
