"""012 Add SSO, audit enhancements, and white-label branding.

Revision ID: 012
Revises: 011
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("merchants", sa.Column("branding", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("merchants", "branding")
