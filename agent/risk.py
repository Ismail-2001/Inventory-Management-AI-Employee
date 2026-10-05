_SEVERITY = {"safe": 0, "warning": 1, "critical": 2}


def _classify(
    days_of_stock_remaining: float,
    lead_time_days: int,
    safety_buffer: float,
) -> tuple[str, str]:
    if days_of_stock_remaining <= lead_time_days:
        return (
            "critical",
            f"Stockout imminent: only {days_of_stock_remaining:.0f} days of stock "
            f"remain, lead time is {lead_time_days} days.",
        )
    if days_of_stock_remaining <= lead_time_days * safety_buffer:
        return (
            "warning",
            f"Stock at risk: {days_of_stock_remaining:.0f} days of stock remaining "
            f"(threshold: {lead_time_days * safety_buffer:.0f}). Reorder soon.",
        )
    return "safe", "Stock levels are adequate."


def determine_risk_level(
    days_of_stock_remaining: float | None,
    lead_time_days: int,
    safety_buffer: float = 1.5,
    days_of_cover_p90: float | None = None,
) -> tuple[str, str]:
    if days_of_stock_remaining is None:
        return "safe", "No sales history — unable to assess risk."

    level, reason = _classify(days_of_stock_remaining, lead_time_days, safety_buffer)

    if days_of_cover_p90 is not None:
        worst_level, _ = _classify(days_of_cover_p90, lead_time_days, safety_buffer)
        if _SEVERITY[worst_level] > _SEVERITY[level]:
            if worst_level == "critical":
                band_reason = (
                    f"Stockout likely under high demand: p90 band leaves only {days_of_cover_p90:.0f} days of cover, "
                    f"lead time is {lead_time_days} days."
                )
            else:
                band_reason = (
                    f"Stock at risk under high demand: p90 band leaves {days_of_cover_p90:.0f} days of cover "
                    f"(threshold: {lead_time_days * safety_buffer:.0f})."
                )
            return worst_level, band_reason

    return level, reason
