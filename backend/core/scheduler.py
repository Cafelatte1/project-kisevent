"""스크랩 주기 실행."""

import os
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from loguru import logger

from backend.core import crawl

SCRAPE_INTERVAL_MIN = int(os.environ.get("SCRAPE_INTERVAL_MIN", "15"))

_scheduler: BackgroundScheduler | None = None


def _publish_next_run() -> None:
    job = _scheduler.get_job("scrape") if _scheduler is not None else None
    next_run = job.next_run_time if job is not None else None
    crawl.set_next_run(next_run.isoformat() if next_run is not None else None)


def _live_job() -> None:
    log = logger.bind(ctx="scheduler")
    log.info("job fired mode=live")
    try:
        crawl.run("live", trigger="scheduler")
    finally:
        _publish_next_run()


def start() -> BackgroundScheduler:
    global _scheduler

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        _live_job,
        "interval",
        minutes=SCRAPE_INTERVAL_MIN,
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(),
        id="scrape",
    )
    _scheduler.start()
    _publish_next_run()
    return _scheduler


def stop(scheduler: BackgroundScheduler) -> None:
    scheduler.shutdown(wait=False)
