import enum
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agent.db import Base


class POStatus(enum.StrEnum):
    draft = "draft"
    pending_approval = "pending_approval"
    approved = "approved"
    rejected = "rejected"
    expired = "expired"


class Sku(Base):
    __tablename__ = "skus"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    shopify_variant_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    merchant_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("merchants.id", ondelete="CASCADE"), index=True)
    sku_code: Mapped[str | None] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(512))
    current_stock: Mapped[int] = mapped_column(Integer, default=0)
    location_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    sales_records: Mapped[list["SalesHistory"]] = relationship(back_populates="sku", cascade="all, delete-orphan")
    forecasts: Mapped[list["Forecast"]] = relationship(back_populates="sku", cascade="all, delete-orphan")
    alerts: Mapped[list["RiskAlert"]] = relationship(back_populates="sku", cascade="all, delete-orphan")


class MerchantTier(enum.StrEnum):
    developer = "developer"
    business = "business"
    enterprise = "enterprise"


TIER_RATE_LIMITS: dict[MerchantTier, str] = {
    MerchantTier.developer: "10/minute",
    MerchantTier.business: "30/minute",
    MerchantTier.enterprise: "100/minute",
}

TIER_DAILY_RUN_LIMITS: dict[MerchantTier, int] = {
    MerchantTier.developer: 100,
    MerchantTier.business: 1000,
    MerchantTier.enterprise: 10000,
}


class Merchant(Base):
    __tablename__ = "merchants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    hashed_api_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    key_prefix: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    shopify_store_domain: Mapped[str] = mapped_column(String(256), nullable=False)
    tier: Mapped[str] = mapped_column(String(16), default=MerchantTier.developer.value)
    branding: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default={})
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SalesHistory(Base):
    __tablename__ = "sales_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku_id: Mapped[int] = mapped_column(Integer, ForeignKey("skus.id", ondelete="CASCADE"), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    units_sold: Mapped[int] = mapped_column(Integer, nullable=False)

    sku: Mapped["Sku"] = relationship(back_populates="sales_records")

    __table_args__ = (
        Index("ix_sales_sku_date", "sku_id", "date"),
        UniqueConstraint("sku_id", "date", name="uq_sales_history_sku_date"),
        {"sqlite_autoincrement": True},
    )


class Forecast(Base):
    __tablename__ = "forecasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku_id: Mapped[int] = mapped_column(Integer, ForeignKey("skus.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    predicted_daily_demand: Mapped[float] = mapped_column(Float, nullable=False)
    days_of_stock_remaining: Mapped[float | None] = mapped_column(Float)
    model_version: Mapped[str] = mapped_column(String(32), default="exp_smoothing_v1")

    sku: Mapped["Sku"] = relationship(back_populates="forecasts")

    __table_args__ = (Index("ix_forecast_sku_created", "sku_id", "created_at"),)


class RiskAlert(Base):
    __tablename__ = "risk_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku_id: Mapped[int] = mapped_column(Integer, ForeignKey("skus.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)

    sku: Mapped["Sku"] = relationship(back_populates="alerts")

    __table_args__ = (Index("ix_risk_sku_resolved", "sku_id", "resolved"),)


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    contact_email: Mapped[str | None] = mapped_column(String(256))
    default_lead_time_days: Mapped[int] = mapped_column(Integer, default=7)
    default_moq: Mapped[int] = mapped_column(Integer, default=1)
    moq_by_sku: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default={})
    unit_cost_by_sku: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default={})
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku_id: Mapped[int] = mapped_column(Integer, ForeignKey("skus.id", ondelete="CASCADE"), nullable=False, index=True)
    merchant_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("merchants.id", ondelete="CASCADE"), index=True)
    supplier_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("suppliers.id", ondelete="SET NULL"))
    status: Mapped[POStatus] = mapped_column(SAEnum(POStatus), nullable=False, default=POStatus.draft)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_cost: Mapped[float] = mapped_column(Float, default=0.0)
    total_cost: Mapped[float] = mapped_column(Float, default=0.0)
    thread_id: Mapped[str | None] = mapped_column(String(64))
    reasoning_text: Mapped[str | None] = mapped_column(Text)
    approved_by: Mapped[str | None] = mapped_column(String(256))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    edited_before_approval: Mapped[bool | None] = mapped_column(Boolean, default=False)
    original_quantity: Mapped[int | None] = mapped_column(Integer)

    sku: Mapped["Sku"] = relationship()
    supplier: Mapped[Optional["Supplier"]] = relationship()

    __table_args__ = (
        Index("ix_po_merchant_status", "merchant_id", "status"),
        Index("ix_po_merchant_created", "merchant_id", "created_at"),
    )


class POOutcome(Base):
    __tablename__ = "po_outcomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    po_id: Mapped[int] = mapped_column(Integer, ForeignKey("purchase_orders.id", ondelete="SET NULL"), nullable=True)
    expected_stockout_prevented: Mapped[bool | None] = mapped_column(Boolean)
    actual_stock_at_delivery: Mapped[int | None] = mapped_column(Integer)
    actual_stockout_occurred: Mapped[bool | None] = mapped_column(Boolean)
    forecast_error_pct: Mapped[float | None] = mapped_column(Float)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReflectionInsight(Base):
    __tablename__ = "reflection_insights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    insight_text: Mapped[str] = mapped_column(Text, nullable=False)
    supporting_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LlmUsage(Base):
    __tablename__ = "llm_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    tokens_in: Mapped[int | None] = mapped_column(Integer)
    tokens_out: Mapped[int | None] = mapped_column(Integer)
    estimated_cost: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_llm_usage_created", "created_at"),)


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    endpoint: Mapped[str | None] = mapped_column(String(256))
    response_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    event_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    event_type: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_webhook_event_type", "event_type"),)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    merchant_id: Mapped[int] = mapped_column(Integer, ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False)
    email: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    hashed_password: Mapped[str | None] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(16), default="staff")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FailedWebhook(Base):
    __tablename__ = "failed_webhooks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str | None] = mapped_column(String(256))
    event_type: Mapped[str | None] = mapped_column(String(128))
    payload_text: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    merchant_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("merchants.id", ondelete="SET NULL"))
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(64))
    target_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_audit_merchant_created", "merchant_id", "created_at"),)
