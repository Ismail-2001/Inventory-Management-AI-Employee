def determine_risk_level(
    days_of_stock_remaining: float | None,
    lead_time_days: int,
    safety_buffer: float = 1.5,
) -> tuple[str, str]:
    if days_of_stock_remaining is None:
        return "safe", "No sales history — unable to assess risk."

    if days_of_stock_remaining <= lead_time_days:
        return (
            "critical",
            f"Stockout imminent: only {days_of_stock_remaining:.0f} days of stock "
            f"remain, lead time is {lead_time_days} days.",
        )
    elif days_of_stock_remaining <= lead_time_days * safety_buffer:
        return (
            "warning",
            f"Stock at risk: {days_of_stock_remaining:.0f} days of stock remaining "
            f"(threshold: {lead_time_days * safety_buffer:.0f}). Reorder soon.",
        )
    else:
        return "safe", "Stock levels are adequate."
