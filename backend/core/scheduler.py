"""스크랩 주기 실행."""

import logging
import os
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from backend.core import crawl, db

SCRAPE_INTERVAL_MIN = int(os.environ.get("SCRAPE_INTERVAL_MIN", "15"))

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None
_backfill_checked = False


def _publish_next_run() -> None:
    job = _scheduler.get_job("scrape") if _scheduler is not None else None
    next_run = job.next_run_time if job is not None else None
    crawl.set_next_run(next_run.isoformat() if next_run is not None else None)


def _backfill_done() -> bool:
    conn = db.connect()
    try:
        return (
            conn.execute(
                "SELECT 1 FROM scrape_runs WHERE mode = 'backfill' AND finished_at IS NOT NULL"
                " AND error IS NULL LIMIT 1"
            ).fetchone()
            is not None
        )
    finally:
        conn.close()


def _live_job() -> None:
    try:
        crawl.run("live", trigger="scheduler")
    finally:
        _publish_next_run()

    global _backfill_checked
    if not _backfill_checked:
        _backfill_checked = True
        if not _backfill_done():
            logger.info("완료된 백필 이력이 없어 1년 백필을 시작한다")
            crawl.start_background("backfill", trigger="scheduler")


def start() -> BackgroundScheduler:
    global _scheduler, _backfill_checked

    _backfill_checked = False
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
    logger.info("스케줄러 시작: %d분 주기", SCRAPE_INTERVAL_MIN)
    return _scheduler


def stop(scheduler: BackgroundScheduler) -> None:
    scheduler.shutdown(wait=False)
