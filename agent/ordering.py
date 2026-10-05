import math
from typing import Any


def planning_daily_demand(
    predicted_daily_demand: float,
    p90_daily_demand: float | None = None,
) -> float:
    if not p90_daily_demand or p90_daily_demand <= 0:
        return predicted_daily_demand
    return max(predicted_daily_demand, p90_daily_demand)


def calculate_reorder_quantity(
    predicted_daily_demand: float,
    current_stock: int,
    lead_time_days: int,
    safety_buffer_days: int = 7,
    moq: int = 1,
    on_order: int = 0,
) -> int:
    if predicted_daily_demand <= 0:
        return 0

    demand_during_lead_time = predicted_daily_demand * (lead_time_days + safety_buffer_days)
    needed = demand_during_lead_time - current_stock - on_order
    quantity = max(0, int(math.ceil(needed)))

    if quantity > 0 and quantity < moq:
        quantity = moq

    return quantity


def build_reasoning_input(
    sku_title: str,
    sku_code: str,
    current_stock: int,
    predicted_daily_demand: float,
    days_of_stock_remaining: float | None,
    lead_time_days: int,
    risk_level: str,
    reorder_quantity: int,
    moq: int,
    p90_daily_demand: float | None = None,
) -> dict[str, Any]:
    inventory: dict[str, Any] = {
        "current_stock": current_stock,
        "predicted_daily_demand": predicted_daily_demand,
        "days_of_stock_remaining": round(days_of_stock_remaining, 1) if days_of_stock_remaining else None,
    }
    if p90_daily_demand is not None:
        inventory["p90_daily_demand"] = p90_daily_demand
    return {
        "product": {"title": sku_title, "sku": sku_code},
        "inventory": inventory,
        "supplier": {"lead_time_days": lead_time_days, "moq": moq},
        "risk_level": risk_level,
        "recommended_reorder_quantity": reorder_quantity,
    }
