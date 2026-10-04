"""Add ensemble forecast columns + inventory_snapshots table (additive).

Revision ID: 015
Revises: 0ac5d8e333f6 (014)
Create Date: 2026-10-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "015"
down_revision: str | None = "0ac5d8e333f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("forecasts", sa.Column("p10_daily_demand", sa.Float(), nullable=True))
    op.add_column("forecasts", sa.Column("p90_daily_demand", sa.Float(), nullable=True))
    op.add_column("forecasts", sa.Column("days_of_cover_p10", sa.Float(), nullable=True))
    op.add_column("forecasts", sa.Column("days_of_cover_p90", sa.Float(), nullable=True))
    op.add_column("forecasts", sa.Column("backtest_wmape", sa.Float(), nullable=True))
    op.add_column("forecasts", sa.Column("backtest_bias", sa.Float(), nullable=True))
    op.add_column("forecasts", sa.Column("horizon_days", sa.Integer(), nullable=True))
    op.add_column(
        "forecasts",
        sa.Column("model_meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    op.create_table(
        "inventory_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("sku_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("stock_level", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["sku_id"], ["skus.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("sku_id", "date", name="uq_inventory_snapshot_sku_date"),
    )


def downgrade() -> None:
    op.drop_table("inventory_snapshots")
    op.drop_column("forecasts", "model_meta")
    op.drop_column("forecasts", "horizon_days")
    op.drop_column("forecasts", "backtest_bias")
    op.drop_column("forecasts", "backtest_wmape")
    op.drop_column("forecasts", "days_of_cover_p90")
    op.drop_column("forecasts", "days_of_cover_p10")
    op.drop_column("forecasts", "p90_daily_demand")
    op.drop_column("forecasts", "p10_daily_demand")
