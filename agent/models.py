import enum
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Enum as SAEnum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agent.db import Base


class POStatus(str, enum.Enum):
    draft = "draft"
    pending_approval = "pending_approval"
    approved = "approved"
    rejected = "rejected"
    expired = "expired"


class Sku(Base):
    __tablename__ = "skus"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    shopify_variant_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    sku_code: Mapped[Optional[str]] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(512))
    current_stock: Mapped[int] = mapped_column(Integer, default=0)
    location_id: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    sales_records: Mapped[list["SalesHistory"]] = relationship(back_populates="sku", cascade="all, delete-orphan")
    forecasts: Mapped[list["Forecast"]] = relationship(back_populates="sku", cascade="all, delete-orphan")
    alerts: Mapped[list["RiskAlert"]] = relationship(back_populates="sku", cascade="all, delete-orphan")


class Merchant(Base):
    __tablename__ = "merchants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    hashed_api_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    shopify_store_domain: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SalesHistory(Base):
    __tablename__ = "sales_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku_id: Mapped[int] = mapped_column(Integer, ForeignKey("skus.id", ondelete="CASCADE"), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    units_sold: Mapped[int] = mapped_column(Integer, nullable=False)

    sku: Mapped["Sku"] = relationship(back_populates="sales_records")


class Forecast(Base):
    __tablename__ = "forecasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku_id: Mapped[int] = mapped_column(Integer, ForeignKey("skus.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    predicted_daily_demand: Mapped[float] = mapped_column(Float, nullable=False)
    days_of_stock_remaining: Mapped[Optional[float]] = mapped_column(Float)
    model_version: Mapped[str] = mapped_column(String(32), default="exp_smoothing_v1")

    sku: Mapped["Sku"] = relationship(back_populates="forecasts")


class RiskAlert(Base):
    __tablename__ = "risk_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku_id: Mapped[int] = mapped_column(Integer, ForeignKey("skus.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)

    sku: Mapped["Sku"] = relationship(back_populates="alerts")


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    contact_email: Mapped[Optional[str]] = mapped_column(String(256))
    default_lead_time_days: Mapped[int] = mapped_column(Integer, default=7)
    moq_by_sku: Mapped[Optional[dict]] = mapped_column(JSONB, default={})
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku_id: Mapped[int] = mapped_column(Integer, ForeignKey("skus.id", ondelete="CASCADE"), nullable=False, index=True)
    supplier_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("suppliers.id", ondelete="SET NULL"))
    status: Mapped[POStatus] = mapped_column(SAEnum(POStatus), nullable=False, default=POStatus.draft)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_cost: Mapped[float] = mapped_column(Float, default=0.0)
    total_cost: Mapped[float] = mapped_column(Float, default=0.0)
    thread_id: Mapped[Optional[str]] = mapped_column(String(64))
    reasoning_text: Mapped[Optional[str]] = mapped_column(Text)
    approved_by: Mapped[Optional[str]] = mapped_column(String(256))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    rejected_reason: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    edited_before_approval: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)
    original_quantity: Mapped[Optional[int]] = mapped_column(Integer)

    sku: Mapped["Sku"] = relationship()
    supplier: Mapped[Optional["Supplier"]] = relationship()


class POOutcome(Base):
    __tablename__ = "po_outcomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    po_id: Mapped[int] = mapped_column(Integer, ForeignKey("purchase_orders.id", ondelete="SET NULL"), nullable=True)
    expected_stockout_prevented: Mapped[Optional[bool]] = mapped_column(Boolean)
    actual_stock_at_delivery: Mapped[Optional[int]] = mapped_column(Integer)
    actual_stockout_occurred: Mapped[Optional[bool]] = mapped_column(Boolean)
    forecast_error_pct: Mapped[Optional[float]] = mapped_column(Float)
    evaluated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class ReflectionInsight(Base):
    __tablename__ = "reflection_insights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    insight_text: Mapped[str] = mapped_column(Text, nullable=False)
    supporting_data: Mapped[Optional[dict]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    merchant_id: Mapped[int] = mapped_column(Integer, ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False)
    email: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    hashed_password: Mapped[Optional[str]] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(16), default="staff")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    merchant_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("merchants.id", ondelete="SET NULL"))
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[Optional[str]] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[Optional[str]] = mapped_column(String(64))
    target_id: Mapped[Optional[str]] = mapped_column(String(64))
    details: Mapped[Optional[dict]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
