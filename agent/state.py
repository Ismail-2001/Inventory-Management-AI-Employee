"""Shared LangGraph state schema for the inventory analysis pipeline."""

from typing import Any, TypedDict


class State(TypedDict, total=False):
    merchant_id: int
    thread_id: str
    skus: list[dict[str, Any]]
    forecasts: list[dict[str, Any]]
    # Engine serving this run (ensemble | exponential | shadow), resolved once
    # at run start from override > merchant flag > default. The node may
    # overwrite it with the effective engine if the circuit breaker trips.
    forecast_engine: str
    forecast_circuit_tripped: bool
    risk_alerts: list[dict[str, Any]]
    purchase_orders: list[dict[str, Any]]
    approval_status: str
    approved_by: str
    notification_summary: str
    confirmation_summary: str
    synced_products: int
    synced_sales: int
