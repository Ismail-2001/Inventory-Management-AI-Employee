from unittest.mock import AsyncMock

import pytest

from agent import scheduler as scheduler_module


@pytest.mark.asyncio
async def test_start_skips_when_env_not_set(monkeypatch):
    monkeypatch.delenv("ENABLE_SCHEDULER", raising=False)
    scheduler_module.scheduler.start = lambda: None
    scheduler_module.scheduler.remove_all_jobs = lambda: None

    scheduler_module.start()

    assert scheduler_module.scheduler.running is False


@pytest.mark.asyncio
async def test_start_adds_jobs_when_enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_SCHEDULER", "true")
    added = []

    def fake_add(func, *a, **kw):
        added.append(kw.get("id", "unknown"))

    monkeypatch.setattr(scheduler_module.scheduler, "add_job", fake_add)
    monkeypatch.setattr(scheduler_module.scheduler, "start", lambda: None)

    scheduler_module.start()

    assert "daily_outcome_eval" in added
    assert "weekly_reflection" in added
    assert "retry_failed_webhooks" in added
    assert "cleanup_old_checkpoints" in added
    assert "export_audit_logs" in added
    assert "daily_forecast_promotions" in added
    assert "weekly_forecast_report" in added


@pytest.mark.asyncio
async def test_daily_outcome_eval_calls_evaluate(monkeypatch):
    called = []

    async def fake_evaluate():
        called.append(True)
        return 3

    monkeypatch.setattr("agent.outcomes.evaluate_pending_outcomes", fake_evaluate)
    monkeypatch.setattr("agent.audit.log", AsyncMock())

    await scheduler_module.daily_outcome_eval()
    assert len(called) == 1


@pytest.mark.asyncio
async def test_export_audit_logs_when_count(monkeypatch):
    monkeypatch.setattr(
        "agent.audit_export.export_audit_logs_to_s3",
        AsyncMock(return_value=5),
    )
    audit_mock = AsyncMock()
    monkeypatch.setattr("agent.audit.log", audit_mock)

    await scheduler_module.export_audit()
    audit_mock.assert_called_once()
    assert audit_mock.call_args.kwargs["details"]["count"] == 5


@pytest.mark.asyncio
async def test_export_audit_no_log_when_zero(monkeypatch):
    monkeypatch.setattr(
        "agent.audit_export.export_audit_logs_to_s3",
        AsyncMock(return_value=0),
    )
    audit_mock = AsyncMock()
    monkeypatch.setattr("agent.audit.log", audit_mock)

    await scheduler_module.export_audit()
    audit_mock.assert_not_called()


@pytest.mark.asyncio
async def test_daily_forecast_promotions_runs_and_logs_promotions(monkeypatch):
    from types import SimpleNamespace

    auto_mock = AsyncMock(return_value=[SimpleNamespace(merchant_id=9, promoted=True)])
    monkeypatch.setattr("agent.forecast_engine.auto_promote_merchants", auto_mock)
    audit_mock = AsyncMock()
    monkeypatch.setattr("agent.audit.log", audit_mock)

    await scheduler_module.daily_forecast_promotions()

    auto_mock.assert_awaited_once()
    audit_mock.assert_awaited_once()
    assert audit_mock.call_args.kwargs["action"] == "forecast_engine_auto_promotions"
    assert audit_mock.call_args.kwargs["details"]["merchant_ids"] == [9]


@pytest.mark.asyncio
async def test_daily_forecast_promotions_no_log_when_nothing_promoted(monkeypatch):
    monkeypatch.setattr(
        "agent.forecast_engine.auto_promote_merchants",
        AsyncMock(return_value=[]),
    )
    audit_mock = AsyncMock()
    monkeypatch.setattr("agent.audit.log", audit_mock)

    await scheduler_module.daily_forecast_promotions()
    audit_mock.assert_not_called()


@pytest.mark.asyncio
async def test_weekly_forecast_report_calls_sender(monkeypatch):
    from datetime import date, timedelta

    sender_mock = AsyncMock(return_value={"merchants": []})
    monkeypatch.setattr("agent.forecast_engine.send_weekly_engine_report", sender_mock)

    await scheduler_module.weekly_forecast_report()

    sender_mock.assert_awaited_once()
    assert sender_mock.call_args.args[0] == date.today() - timedelta(days=7)
