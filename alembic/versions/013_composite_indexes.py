"""013 Add composite indexes for hot query paths.

Revision ID: 013
Revises: 012
"""
from alembic import op

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_sales_sku_date", "sales_history", ["sku_id", "date"])
    op.create_index("ix_po_merchant_status", "purchase_orders", ["merchant_id", "status"])
    op.create_index("ix_po_merchant_created", "purchase_orders", ["merchant_id", "created_at"])
    op.create_index("ix_risk_sku_resolved", "risk_alerts", ["sku_id", "resolved"])
    op.create_index("ix_forecast_sku_created", "forecasts", ["sku_id", "created_at"])
    op.create_index("ix_llm_usage_created", "llm_usage", ["created_at"])
    op.create_index("ix_audit_merchant_created", "audit_log", ["merchant_id", "created_at"])
    op.create_index("ix_webhook_event_type", "webhook_events", ["event_type"])


def downgrade() -> None:
    op.drop_index("ix_webhook_event_type", "webhook_events")
    op.drop_index("ix_audit_merchant_created", "audit_log")
    op.drop_index("ix_llm_usage_created", "llm_usage")
    op.drop_index("ix_forecast_sku_created", "forecasts")
    op.drop_index("ix_risk_sku_resolved", "risk_alerts")
    op.drop_index("ix_po_merchant_created", "purchase_orders")
    op.drop_index("ix_po_merchant_status", "purchase_orders")
    op.drop_index("ix_sales_sku_date", "sales_history")
