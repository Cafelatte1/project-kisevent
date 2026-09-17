"""대시보드가 쓰는 REST."""

import json
import threading

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from backend.core import db, queries, scraper
from backend.core.scheduler import SCRAPE_INTERVAL_MIN

router = APIRouter(prefix="/api")

_scrape_lock = threading.Lock()


@router.get("/health")
def health() -> dict:
    conn = db.connect()
    try:
        last_run = conn.execute("SELECT * FROM scrape_runs ORDER BY id DESC LIMIT 1").fetchone()
        return {
            "ok": True,
            "last_run": dict(last_run) if last_run is not None else None,
            "pending_images": queries.pending_images(conn),
        }
    finally:
        conn.close()


@router.get("/stats")
def stats(request: Request) -> dict:
    conn = db.connect()
    try:
        by_target = {"영업점": 0, "뱅키스": 0}
        events_active = 0
        for row in conn.execute("SELECT targets FROM events WHERE active = 1"):
            events_active += 1
            for target in json.loads(row["targets"]):
                if target in by_target:
                    by_target[target] += 1

        runs = queries.recent_runs(conn, 1)
        job = request.app.state.scheduler.get_job("scrape")
        next_run = job.next_run_time if job is not None else None

        return {
            "events_active": events_active,
            "by_target": by_target,
            "images": queries.image_status_counts(conn),
            "new_last_24h": queries.new_events_since(conn, 24),
            "last_run": runs[0] if runs else None,
            "next_run_at": next_run.isoformat() if next_run is not None else None,
            "interval_min": SCRAPE_INTERVAL_MIN,
        }
    finally:
        conn.close()


@router.get("/events")
def events(target: str | None = None) -> dict:
    conn = db.connect()
    try:
        return queries.list_events(conn, target)
    finally:
        conn.close()


@router.get("/events/{num}")
def event(num: str) -> dict:
    conn = db.connect()
    try:
        detail = queries.event_detail(conn, num)
        if detail is None:
            raise HTTPException(status_code=404, detail="not found")
        return detail
    finally:
        conn.close()


@router.get("/runs")
def runs(limit: int = 20) -> list[dict]:
    conn = db.connect()
    try:
        return queries.recent_runs(conn, limit)
    finally:
        conn.close()


@router.post("/scrape")
async def scrape():
    if not _scrape_lock.acquire(blocking=False):
        return JSONResponse(status_code=409, content={"error": "already running"})
    try:
        return await run_in_threadpool(scraper.run_once)
    finally:
        _scrape_lock.release()
