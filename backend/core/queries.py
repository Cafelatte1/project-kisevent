"""MCP tool과 REST가 함께 쓰는 조회 함수."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

PENDING_SUMMARY_SQL = (
    "SELECT COUNT(*) FROM event_images i WHERE i.status NOT IN ('superseded', 'failed')"
    " AND NOT EXISTS (SELECT 1 FROM image_summary s WHERE s.image_id = i.id)"
)
LATEST_IMAGE_SQL = (
    "SELECT id, status, local_path FROM event_images WHERE event_num = ? AND status != 'superseded'"
    " ORDER BY id DESC LIMIT 1"
)
IMAGE_STATUSES = ("pending", "summarized", "failed")
TARGET_LABELS = ("영업점", "뱅키스", "연금", "미상")


def pending_summaries(conn) -> int:
    return conn.execute(PENDING_SUMMARY_SQL).fetchone()[0]


def _image_summary(conn, image_id: int):
    return conn.execute(
        "SELECT json, target_types FROM image_summary WHERE image_id = ?", (image_id,)
    ).fetchone()


def _event_view(conn, row) -> dict:
    """목록·일자 조회가 함께 쓰는 이벤트 한 건. 대상은 배너 요약(v2)에서 온다."""
    image = conn.execute(LATEST_IMAGE_SQL, (row["num"],)).fetchone()
    summary = _image_summary(conn, image["id"]) if image is not None else None

    return {
        "num": row["num"],
        "title": row["title"],
        "state": row["state"],
        "target_types": json.loads(summary["target_types"]) if summary is not None else None,
        "period_start": row["period_start"],
        "period_end": row["period_end"],
        "summary": json.loads(summary["json"]) if summary is not None else None,
        "summary_status": "none" if summary is None else "summarized",
        "template": row["template"],
    }


def _matches_target(target_types: list[str] | None, target: str | None) -> bool:
    """요약이 없는 이벤트(target_types null)는 대상이 그 target일 수 있으므로 통과시킨다."""
    if not target:
        return True
    if target_types is None:
        return True
    return target in target_types


def list_events(conn, target: str | None = None, state: str = "ongoing") -> dict:
    events = []
    where = "" if state == "all" else " WHERE state = ?"
    params = () if state == "all" else (state,)
    for row in conn.execute(f"SELECT * FROM events{where} ORDER BY num DESC", params):
        event = _event_view(conn, row)
        if _matches_target(event["target_types"], target):
            events.append(event)

    last_run = conn.execute(
        "SELECT finished_at FROM scrape_runs WHERE finished_at IS NOT NULL ORDER BY id DESC LIMIT 1"
    ).fetchone()

    pending = [event["num"] for event in events if event["summary_status"] == "none"]

    return {
        "fetched_at": last_run["finished_at"] if last_run is not None else None,
        "pending_summaries": len(pending),
        "pending_event_nums": pending,
        "count": len(events),
        "events": events,
    }


def events_on(conn, date_str: str, target: str | None = None) -> list[dict]:
    """그 날짜에 신청 기간이 걸려 있던 이벤트(종료 포함). 목록 날짜는 YYYY.MM.DD라 변환해 비교한다."""
    rows = conn.execute(
        "SELECT * FROM events WHERE replace(period_start, '.', '-') <= ?"
        " AND replace(period_end, '.', '-') >= ?"
        " ORDER BY CASE WHEN state = 'ongoing' THEN 0 ELSE 1 END,"
        " replace(period_end, '.', '-') DESC",
        (date_str, date_str),
    ).fetchall()

    events = [_event_view(conn, row) for row in rows]
    return [event for event in events if _matches_target(event["target_types"], target)]


def by_target(conn) -> dict:
    """진행 중 이벤트의 대상 분포. 요약이 없거나 대상을 못 고른 이벤트는 미상으로 센다."""
    counts = {label: 0 for label in TARGET_LABELS}
    for row in conn.execute("SELECT * FROM events WHERE state = 'ongoing'"):
        for label in _event_view(conn, row)["target_types"] or ["미상"]:
            if label in counts:
                counts[label] += 1
    return counts


def event_detail(conn, num: str) -> dict | None:
    row = conn.execute("SELECT * FROM events WHERE num = ?", (num,)).fetchone()
    if row is None:
        return None

    event = dict(row)
    del event["targets"]
    event["list_summary"] = event.pop("summary")
    event["summary"] = None
    event["actions"] = json.loads(row["actions"] or "[]")

    image = conn.execute(LATEST_IMAGE_SQL, (num,)).fetchone()
    if image is None:
        event["image"] = None
        return event

    summary = _image_summary(conn, image["id"])
    if summary is not None:
        event["summary"] = json.loads(summary["json"])

    event["image"] = {
        "image_id": image["id"],
        "status": image["status"],
        "image_url": f"/images/{Path(image['local_path']).name}",
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
