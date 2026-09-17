"""스크랩 주기 실행."""

import logging
import os
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from backend.core import scraper

SCRAPE_INTERVAL_MIN = int(os.environ.get("SCRAPE_INTERVAL_MIN", "15"))

logger = logging.getLogger(__name__)


def start() -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        scraper.run_once,
        "interval",
        minutes=SCRAPE_INTERVAL_MIN,
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(),
        id="scrape",
    )
    scheduler.start()
    logger.info("스케줄러 시작: %d분 주기", SCRAPE_INTERVAL_MIN)
    return scheduler


def stop(scheduler: BackgroundScheduler) -> None:
    scheduler.shutdown(wait=False)
