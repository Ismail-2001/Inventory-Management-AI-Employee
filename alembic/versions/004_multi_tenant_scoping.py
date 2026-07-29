"""Add merchant_id to skus and purchase_orders for multi-tenant scoping

Revision ID: 004
Revises: 003
Create Date: 2026-07-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable first so this is safe to run against existing single-tenant
    # data. Backfill to the single existing merchant, then a follow-up
    # migration should tighten this to NOT NULL once every row is tagged -
    # deliberately not done in the same migration as the backfill, since a
    # bad backfill assumption (multiple untagged merchants) should not be
    # silently forced NOT NULL in one step.
    op.add_column("skus", sa.Column("merchant_id", sa.Integer(), sa.ForeignKey("merchants.id", ondelete="CASCADE"), nullable=True))
    op.create_index("ix_skus_merchant_id", "skus", ["merchant_id"])

    op.add_column("purchase_orders", sa.Column("merchant_id", sa.Integer(), sa.ForeignKey("merchants.id", ondelete="CASCADE"), nullable=True))
    op.create_index("ix_purchase_orders_merchant_id", "purchase_orders", ["merchant_id"])

    # sales_history, forecasts, risk_alerts stay scoped indirectly via
    # sku.merchant_id (they all join through sku_id) - this is a normalization
    # choice, not an oversight: duplicating merchant_id onto every child table
    # adds write-path complexity without adding query capability, since every
    # real query already needs the sku row anyway.

    op.execute(
        """
        UPDATE skus SET merchant_id = (SELECT id FROM merchants ORDER BY id LIMIT 1)
        WHERE merchant_id IS NULL AND EXISTS (SELECT 1 FROM merchants)
        """
    )
    op.execute(
        """
        UPDATE purchase_orders SET merchant_id = (
            SELECT s.merchant_id FROM skus s WHERE s.id = purchase_orders.sku_id
        )
        WHERE merchant_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_purchase_orders_merchant_id", table_name="purchase_orders")
    op.drop_column("purchase_orders", "merchant_id")
    op.drop_index("ix_skus_merchant_id", table_name="skus")
    op.drop_column("skus", "merchant_id")
