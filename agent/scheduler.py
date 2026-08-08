import os

from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()


async def daily_outcome_eval() -> None:
    from agent.outcomes import evaluate_pending_outcomes

    count = await evaluate_pending_outcomes()
    if count:
        from agent.audit import log
        await log(action="outcome_evaluation", details={"evaluated": count})


async def weekly_reflection() -> None:
    from datetime import date, timedelta

    from agent.nodes.reflection_node import run_reflection
    from agent.nodes.reporting_node import run_reporting

    week_start = date.today() - timedelta(days=7)
    insights = await run_reflection(week_start)
    await run_reporting(week_start, insights)


async def retry_webhooks() -> None:
    from agent.webhooks import retry_failed_webhooks
    await retry_failed_webhooks()


async def cleanup_sessions() -> None:
    from agent.db import cleanup_old_checkpoints
    await cleanup_old_checkpoints()


async def export_audit() -> None:
    from agent.audit_export import export_audit_logs_to_s3
    count = await export_audit_logs_to_s3()
    if count:
        from agent.audit import log
        await log(action="audit_export", details={"count": count})


def start() -> None:
    if os.getenv("ENABLE_SCHEDULER", "").lower() not in ("1", "true", "yes"):
        return
    scheduler.add_job(daily_outcome_eval, "interval", hours=24, id="daily_outcome_eval")
    scheduler.add_job(
        weekly_reflection, "cron", day_of_week="mon", hour=8, minute=0, id="weekly_reflection"
    )
    scheduler.add_job(retry_webhooks, "interval", minutes=15, id="retry_failed_webhooks")
    scheduler.add_job(cleanup_sessions, "interval", days=1, id="cleanup_old_checkpoints")
    scheduler.add_job(export_audit, "interval", hours=24, id="export_audit_logs")
    scheduler.start()
