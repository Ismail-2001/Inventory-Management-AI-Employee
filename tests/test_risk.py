from agent.risk import determine_risk_level


def test_critical_when_below_lead_time():
    level, reason = determine_risk_level(5.0, lead_time_days=7)
    assert level == "critical"
    assert "Stockout imminent" in reason


def test_warning_when_below_safety_buffer():
    level, reason = determine_risk_level(10.0, lead_time_days=7, safety_buffer=1.5)
    assert level == "warning"
    assert "Stock at risk" in reason


def test_safe_when_above_threshold():
    level, reason = determine_risk_level(20.0, lead_time_days=7, safety_buffer=1.5)
    assert level == "safe"


def test_safe_when_no_data():
    level, reason = determine_risk_level(None, lead_time_days=7)
    assert level == "safe"
    assert "No sales history" in reason


def test_critical_edge_case():
    level, reason = determine_risk_level(7.0, lead_time_days=7)
    assert level == "critical"


def test_warning_edge_case():
    level, reason = determine_risk_level(10.5, lead_time_days=7, safety_buffer=1.5)
    assert level == "warning"


def test_p90_band_escalates_to_critical():
    level, reason = determine_risk_level(20.0, lead_time_days=7, days_of_cover_p90=4.0)
    assert level == "critical"
    assert "p90" in reason
    assert "Stockout likely" in reason


def test_p90_band_escalates_to_warning():
    level, reason = determine_risk_level(20.0, lead_time_days=7, days_of_cover_p90=10.0)
    assert level == "warning"
    assert "p90" in reason
    assert "Stock at risk under high demand" in reason


def test_p90_band_never_downgrades():
    level, reason = determine_risk_level(10.0, lead_time_days=7, days_of_cover_p90=20.0)
    assert level == "warning"
    assert "p90" not in reason


def test_p90_band_keeps_point_reason_when_levels_equal():
    level, reason = determine_risk_level(5.0, lead_time_days=7, days_of_cover_p90=3.0)
    assert level == "critical"
    assert "Stockout imminent" in reason


def test_p90_band_ignored_without_point_forecast():
    level, reason = determine_risk_level(None, lead_time_days=7, days_of_cover_p90=4.0)
    assert level == "safe"
    assert "No sales history" in reason
