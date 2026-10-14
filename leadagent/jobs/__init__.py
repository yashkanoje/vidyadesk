from apscheduler.schedulers.background import BackgroundScheduler

from leadagent.jobs.digest import run_digests
from leadagent.jobs.nudge import run_nudges


def start_scheduler() -> BackgroundScheduler:
    """Start the two jobs in background threads. The app must run as a single process, or every job runs twice."""
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(run_nudges, "interval", minutes=15, id="nudges", max_instances=1, coalesce=True)
    # A summary that misses its slot by more than 15 minutes is skipped for that day.
    scheduler.add_job(run_digests, "cron", minute="0,30", id="digests", misfire_grace_time=900, coalesce=True)
    scheduler.start()
    return scheduler
