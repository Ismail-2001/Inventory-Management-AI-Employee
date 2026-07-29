from datetime import date, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from agent.config import settings

scheduler = AsyncIOScheduler()


async def daily_outcome_eval():
    from agent.outcomes import evaluate_pending_outcomes

    count = await evaluate_pending_outcomes()
    if count:
        from agent.audit import log
        await log(action="outcome_evaluation", details={"evaluated": count})


async def weekly_reflection():
    from datetime import timedelta

    from agent.nodes.reflection_node import run_reflection
    from agent.nodes.reporting_node import run_reporting

    week_start = date.today() - timedelta(days=7)
    insights = await run_reflection(week_start)
    await run_reporting(week_start, insights)


def start():
    scheduler.add_job(daily_outcome_eval, "interval", hours=24, id="daily_outcome_eval")
    scheduler.add_job(
        weekly_reflection, "cron", day_of_week="mon", hour=8, minute=0, id="weekly_reflection"
    )
    scheduler.start()
