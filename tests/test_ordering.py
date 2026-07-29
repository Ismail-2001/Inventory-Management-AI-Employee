import pytest
from agent.ordering import calculate_reorder_quantity


def test_basic_reorder():
    qty = calculate_reorder_quantity(
        predicted_daily_demand=10.0,
        current_stock=50,
        lead_time_days=7,
        safety_buffer_days=7,
    )
    assert qty == 90


def test_no_reorder_needed():
    qty = calculate_reorder_quantity(
        predicted_daily_demand=5.0,
        current_stock=200,
        lead_time_days=7,
        safety_buffer_days=7,
    )
    assert qty == 0


def test_moq_round_up():
    qty = calculate_reorder_quantity(
        predicted_daily_demand=3.0,
        current_stock=10,
        lead_time_days=7,
        safety_buffer_days=7,
        moq=50,
    )
    assert qty == 50


def test_on_order_reduces_quantity():
    qty = calculate_reorder_quantity(
        predicted_daily_demand=10.0,
        current_stock=50,
        lead_time_days=7,
        safety_buffer_days=7,
        on_order=30,
    )
    assert qty == 60


def test_zero_demand():
    qty = calculate_reorder_quantity(
        predicted_daily_demand=0.0,
        current_stock=10,
        lead_time_days=7,
    )
    assert qty == 0


def test_partial_lead_time():
    qty = calculate_reorder_quantity(
        predicted_daily_demand=5.0,
        current_stock=25,
        lead_time_days=3,
        safety_buffer_days=2,
        moq=10,
    )
    assert qty == 0
