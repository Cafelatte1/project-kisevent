"""대시보드가 쓰는 REST."""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from backend.core import crawl, db, queries, scraper
from backend.core.scheduler import SCRAPE_INTERVAL_MIN

router = APIRouter(prefix="/api")


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
def stats() -> dict:
    conn = db.connect()
    try:
        events_active = conn.execute(
            "SELECT COUNT(*) FROM events WHERE state = 'ongoing'"
        ).fetchone()[0]
        events_ended = conn.execute(
            "SELECT COUNT(*) FROM events WHERE state = 'ended'"
        ).fetchone()[0]
        runs = queries.recent_runs(conn, 1)
        status = crawl.snapshot()

        images = queries.image_status_counts(conn)
        images["pending_summaries"] = queries.pending_summaries(conn)

        return {
            "events_active": events_active,
            "events_ended": events_ended,
            "by_target": queries.by_target(conn),
            "images": images,
            "new_last_24h": queries.new_events_since(conn, 24),
            "last_run": runs[0] if runs else None,
            "next_run_at": status["next_run_at"],
            "interval_min": SCRAPE_INTERVAL_MIN,
            "crawl": status,
        }
    finally:
        conn.close()


@router.get("/events")
def events(target: str | None = None, state: str = "ongoing") -> dict:
    conn = db.connect()
    try:
        return queries.list_events(conn, target, state)
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


@router.get("/crawl/status")
def crawl_status() -> dict:
    return crawl.snapshot()


@router.post("/scrape")
def scrape(mode: str = "live"):
    if mode not in scraper.LIST_TAB:
        return JSONResponse(status_code=400, content={"error": "mode must be live or backfill"})
    try:
        crawl.start_background(mode, "manual")
    except crawl.AlreadyRunning:
        return JSONResponse(status_code=409, content={"error": "already running"})
    except crawl.Debounced as exc:
        return JSONResponse(
            status_code=429,
            content={"error": "too soon", "retry_after_sec": exc.retry_after_sec},
            headers={"Retry-After": str(exc.retry_after_sec)},
        )
    return JSONResponse(status_code=202, content={"started": True, "mode": mode})
