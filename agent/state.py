"""Shared LangGraph state schema for the inventory analysis pipeline."""

from typing import Any, TypedDict


class State(TypedDict, total=False):
    merchant_id: int
    thread_id: str
    skus: list[dict[str, Any]]
    forecasts: list[dict[str, Any]]
    risk_alerts: list[dict[str, Any]]
    purchase_orders: list[dict[str, Any]]
    approval_status: str
    approved_by: str
    notification_summary: str
    confirmation_summary: str
    synced_products: int
    synced_sales: int
