"""Initial schema: skus, sales_history, forecasts, risk_alerts

Revision ID: 001
Revises:
Create Date: 2026-07-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "skus",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("shopify_variant_id", sa.String(64), nullable=False),
        sa.Column("sku_code", sa.String(128), nullable=True),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("current_stock", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("location_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("shopify_variant_id"),
    )
    op.create_index("ix_skus_shopify_variant_id", "skus", ["shopify_variant_id"])

    op.create_table(
        "sales_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("sku_id", sa.Integer(), sa.ForeignKey("skus.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("units_sold", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sales_history_sku_id", "sales_history", ["sku_id"])

    op.create_table(
        "forecasts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("sku_id", sa.Integer(), sa.ForeignKey("skus.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("predicted_daily_demand", sa.Float(), nullable=False),
        sa.Column("days_of_stock_remaining", sa.Float(), nullable=True),
        sa.Column("model_version", sa.String(32), nullable=False, server_default="exp_smoothing_v1"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_forecasts_sku_id", "forecasts", ["sku_id"])

    op.create_table(
        "risk_alerts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("sku_id", sa.Integer(), sa.ForeignKey("skus.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("risk_level", sa.String(16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default="false"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_risk_alerts_sku_id", "risk_alerts", ["sku_id"])


    op.create_table(
        "merchants",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("hashed_api_key", sa.String(128), nullable=False),
        sa.Column("shopify_store_domain", sa.String(256), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("hashed_api_key"),
    )
    op.create_index("ix_merchants_hashed_api_key", "merchants", ["hashed_api_key"])


def downgrade() -> None:
    op.drop_table("merchants")
    op.drop_table("risk_alerts")
    op.drop_table("forecasts")
    op.drop_table("sales_history")
    op.drop_table("skus")
