"""Add tier column to merchants table and create MerchantTier enum.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-29
"""

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE TYPE merchanttier AS ENUM ('developer', 'business', 'enterprise')")
        op.add_column(
            "merchants",
            sa.Column(
                "tier",
                sa.Enum("developer", "business", "enterprise", name="merchanttier"),
                nullable=False,
                server_default="developer",
            ),
        )
    else:
        op.add_column(
            "merchants",
            sa.Column("tier", sa.String(20), nullable=False, server_default="developer"),
        )


def downgrade() -> None:
    op.drop_column("merchants", "tier")
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TYPE merchanttier")
