"""MCP tool과 REST가 함께 쓰는 조회 함수."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

PENDING_SQL = "SELECT COUNT(*) FROM event_images WHERE status NOT IN ('analyzed', 'superseded', 'failed')"
LATEST_IMAGE_SQL = (
    "SELECT id, status, local_path FROM event_images WHERE event_num = ? AND status != 'superseded'"
    " ORDER BY id DESC LIMIT 1"
)
IMAGE_STATUSES = ("pending", "transcribing", "transcribed", "analyzed", "failed")


def pending_images(conn) -> int:
    return conn.execute(PENDING_SQL).fetchone()[0]


def transcript(conn, image_id: int) -> str:
    rows = conn.execute(
        "SELECT text FROM image_tiles WHERE image_id = ? ORDER BY idx", (image_id,)
    ).fetchall()
    return "\n\n".join(row["text"] or "" for row in rows)


def list_events(conn, target: str | None = None, state: str = "ongoing") -> dict:
    events = []
    where = "" if state == "all" else " WHERE state = ?"
    params = () if state == "all" else (state,)
    for row in conn.execute(f"SELECT * FROM events{where} ORDER BY num DESC", params):
        targets = json.loads(row["targets"])
        if target and target not in targets:
            continue

        image = conn.execute(LATEST_IMAGE_SQL, (row["num"],)).fetchone()
        analysis = None
        if image is not None:
            analysis = conn.execute(
                "SELECT summary FROM image_analysis WHERE image_id = ?", (image["id"],)
            ).fetchone()

        events.append(
            {
                "num": row["num"],
                "title": row["title"],
                "state": row["state"],
                "targets": targets,
                "period_start": row["period_start"],
                "period_end": row["period_end"],
                "summary": row["summary"],
                "template": row["template"],
                "analysis_status": image["status"] if image is not None else None,
                "analysis_summary": analysis["summary"] if analysis is not None else None,
            }
        )

    last_run = conn.execute(
        "SELECT finished_at FROM scrape_runs WHERE finished_at IS NOT NULL ORDER BY id DESC LIMIT 1"
    ).fetchone()

    return {
        "fetched_at": last_run["finished_at"] if last_run is not None else None,
        "pending_images": pending_images(conn),
        "count": len(events),
        "events": events,
    }


def event_detail(conn, num: str) -> dict | None:
    row = conn.execute("SELECT * FROM events WHERE num = ?", (num,)).fetchone()
    if row is None:
        return None

    event = dict(row)
    event["targets"] = json.loads(row["targets"])
    event["actions"] = json.loads(row["actions"] or "[]")

    image = conn.execute(LATEST_IMAGE_SQL, (num,)).fetchone()
    if image is None:
        event["image"] = None
        return event

    analysis = conn.execute(
        "SELECT summary, json FROM image_analysis WHERE image_id = ?", (image["id"],)
    ).fetchone()
    event["image"] = {
        "image_id": image["id"],
        "status": image["status"],
        "image_url": f"/images/{Path(image['local_path']).name}",
        "analysis": json.loads(analysis["json"]) if analysis is not None else None,
        "summary": analysis["summary"] if analysis is not None else None,
        "transcript": transcript(conn, image["id"]),
    }
    return event


def image_status_counts(conn) -> dict:
    counts = {status: 0 for status in IMAGE_STATUSES}
    for row in conn.execute(
        "SELECT status, COUNT(*) AS n FROM event_images WHERE status != 'superseded' GROUP BY status"
    ):
        counts[row["status"]] = row["n"]
    return counts


def recent_runs(conn, limit: int = 20) -> list[dict]:
    runs = []
    for row in conn.execute("SELECT * FROM scrape_runs ORDER BY id DESC LIMIT ?", (limit,)):
        run = dict(row)
        if run["finished_at"]:
            started = datetime.fromisoformat(run["started_at"])
            finished = datetime.fromisoformat(run["finished_at"])
            run["duration_sec"] = round((finished - started).total_seconds(), 1)
        else:
            run["duration_sec"] = None
        runs.append(run)
    return runs


def new_events_since(conn, hours: int = 24) -> int:
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    return conn.execute(
        "SELECT COUNT(*) FROM events WHERE state = 'ongoing' AND first_seen_at >= ?", (since,)
    ).fetchone()[0]
