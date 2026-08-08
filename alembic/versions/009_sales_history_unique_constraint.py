"""Add a unique constraint for sales history rows

Revision ID: 009
Revises: 008
Create Date: 2026-07-16
"""

from collections.abc import Sequence

from alembic import op

revision: str = "009"
down_revision: str | None = "008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint("uq_sales_history_sku_date", "sales_history", ["sku_id", "date"])


def downgrade() -> None:
    op.drop_constraint("uq_sales_history_sku_date", "sales_history", type_="unique")
