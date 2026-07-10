"""Add suppliers and purchase_orders tables

Revision ID: 002
Revises: 001
Create Date: 2026-07-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "suppliers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("contact_email", sa.String(256), nullable=True),
        sa.Column("default_lead_time_days", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("moq_by_sku", JSONB(), nullable=True, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "purchase_orders",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("sku_id", sa.Integer(), sa.ForeignKey("skus.id", ondelete="CASCADE"), nullable=False),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            "status",
            sa.Enum("draft", "pending_approval", "approved", "rejected", "expired", name="postatus"),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_cost", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("total_cost", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("thread_id", sa.String(64), nullable=True),
        sa.Column("reasoning_text", sa.Text(), nullable=True),
        sa.Column("approved_by", sa.String(256), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_purchase_orders_sku_id", "purchase_orders", ["sku_id"])


def downgrade() -> None:
    op.drop_table("purchase_orders")
    op.drop_table("suppliers")
    sa.Enum(name="postatus").drop(op.get_bind(), checkfirst=True)
