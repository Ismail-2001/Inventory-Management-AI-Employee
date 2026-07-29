"""Add a unique constraint for sales history rows

Revision ID: 009
Revises: 008
Create Date: 2026-07-16
"""
from typing import Sequence, Union

from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint("uq_sales_history_sku_date", "sales_history", ["sku_id", "date"])


def downgrade() -> None:
    op.drop_constraint("uq_sales_history_sku_date", "sales_history", type_="unique")
