"""Claude Desktop이 붙는 MCP tool 정의."""

import asyncio
import base64
import functools
import inspect
import json
import time
from datetime import datetime, timedelta, timezone

from loguru import logger
from mcp.server.mcpserver import MCPServer
from mcp.types import ContentBlock, ImageContent, TextContent
from pydantic import ValidationError

import httpx

from backend.core import crawl, db, queries, tiles
from backend.mcp.schema import SUMMARY_GUIDE, SUMMARY_SCHEMA_VERSION, SummaryV2

INSTRUCTIONS = (
    "Korea Investment & Securities (한국투자증권) event collector and summarizer. Event content lives inside"
    " banner images, so the relevant banners must be summarized before you answer. Flow: call sync_now once"
    " before the first event query of a conversation (it waits for the collection to finish, so query right"
    " after) → pick events with list_events or events_on → if anything is unsummarized, take the image_id"
    " batches from the sync_now response (or list_pending_summaries) → where subagents are available"
    " (Claude Code, Codex) spawn one event-analyzer per batch, all at once. The main session must not call"
    " get_summary_tiles itself and work through images sequentially; the only exception is Claude Desktop,"
    " which has no subagents → query again and answer. Do not call sync_now again in the same conversation."
)

mcp = MCPServer("kis-event", instructions=INSTRUCTIONS)

# stdio(Claude Desktop)는 서버와 다른 프로세스라 실행 게이트를 공유하지 못한다. 그 경우 sync_now는
# 서버 REST에 위임한다(backend.mcp.stdio가 True로 바꾼다).
SYNC_VIA_HTTP = False
SERVER_URL = "http://127.0.0.1:4000"
SYNC_WAIT_SEC = 60
BATCH_SIZE = 2  # 서브에이전트 하나가 맡는 이미지 수
SUBAGENT_NEXT = (
    "Spawn one event-analyzer subagent per batch, all at the same time. The main session must not call"
    " get_summary_tiles itself; only where no subagents exist (Claude Desktop) run get_summary_tiles →"
    " save_summary per image_id directly."
)

CLAIM_TIMEOUT_MIN = 30
SUMMARY_QUALITY = 75
SUMMARY_CANDIDATE_SQL = (
    "SELECT i.id, i.local_path, i.event_num, e.title, e.summary, e.period_start, e.period_end,"
    " e.template"
    " FROM event_images i JOIN events e ON e.num = i.event_num"
    " WHERE i.status NOT IN ('superseded', 'failed')"
    " AND NOT EXISTS (SELECT 1 FROM image_summary s WHERE s.image_id = i.id)"
    " AND (i.summary_claimed_at IS NULL OR i.summary_claimed_at < ?)"
)
SUMMARY_IMAGE_SQL = (
    "SELECT i.id, i.local_path, i.event_num, e.title, e.summary, e.period_start, e.period_end,"
    " e.template"
    " FROM event_images i JOIN events e ON e.num = i.event_num"
    " WHERE i.status != 'superseded' AND i.id = ?"
)
SUMMARY_ORDER_SQL = (
    " ORDER BY CASE WHEN e.state = 'ongoing' THEN 0 ELSE 1 END,"
    " replace(e.period_end, '.', '-') DESC"
)


log = logger.bind(ctx="mcp")

# 이미지 bytes·JSON 본문은 로그에 넣지 않는다
KEY_ARGS = ("image_id", "event_num", "event_nums", "target", "date", "limit", "num")


def _logged(func):
    """tool 호출 한 줄: 이름·핵심 인자·소요 시간."""
    signature = inspect.signature(func)

    def _log(started: float, args, kwargs) -> None:
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        shown = " ".join(
            f"{name}={bound.arguments[name]}"
            for name in KEY_ARGS
            if bound.arguments.get(name) is not None
        )
        log.info(
            "tool={}{} elapsed={}s",
            func.__name__,
            f" {shown}" if shown else "",
            round(time.monotonic() - started, 3),
        )

    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            started = time.monotonic()
            try:
                return await func(*args, **kwargs)
            finally:
                _log(started, args, kwargs)

        return async_wrapper

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        started = time.monotonic()
        try:
            return func(*args, **kwargs)
        finally:
            _log(started, args, kwargs)

    return wrapper


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _claim_cutoff() -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=CLAIM_TIMEOUT_MIN)).isoformat()


def _ongoing_pending_plan() -> dict:
    conn = db.connect()
    try:
        return _pending_plan(_pending_rows(conn, ongoing_only=True))
    finally:
        conn.close()


def _sync_result(snapshot: dict) -> dict:
    if snapshot.get("last_error"):
        return {"synced": False, "error": snapshot["last_error"]}
    result = snapshot.get("last_result") or {}
    plan = _ongoing_pending_plan()
    return {
        "synced": True,
        "events": result.get("events"),
        "new": result.get("new"),
        "updated": result.get("updated"),
        "finished_at": snapshot.get("last_finished_at"),
        "pending_summaries": plan["pending"],
        "batches": plan["batches"],
        **({"next": plan["next"]} if "next" in plan else {}),
    }


async def _wait_idle(get_snapshot) -> dict:
    deadline = time.monotonic() + SYNC_WAIT_SEC
    while time.monotonic() < deadline:
        snapshot = await get_snapshot()
        if snapshot.get("state") != "running":
            return _sync_result(snapshot)
        await asyncio.sleep(0.5)
    return {"synced": False, "error": f"The collection did not finish within {SYNC_WAIT_SEC}s. Query again in a moment."}


@mcp.tool()
@_logged
async def sync_now() -> dict:
    """Re-collect the list of ongoing events now (live sync). Call it once before the first event query of a conversation. It waits for the collection to finish (usually ~5s) and returns the result, so call list_events/events_on right after. When synced is true you get new (new events), updated (changed events) and batches: the unsummarized image_ids of ongoing events, pre-split into groups of two. If batches is not empty, finish the summaries before querying by following next — spawn one event-analyzer subagent per batch in parallel (the main session does not call get_summary_tiles itself). retry_after_sec means the last collection was under a minute ago, so the data is already fresh: just query. already_running means another collection is in progress: query a few seconds later. Do not call it again in the same conversation. Backfilling past events is done only from the dashboard."""
    if SYNC_VIA_HTTP:
        async with httpx.AsyncClient(base_url=SERVER_URL, timeout=10.0) as client:
            try:
                res = await client.post("/api/scrape", params={"mode": "live"})
            except httpx.HTTPError:
                return {"synced": False, "error": f"The server at {SERVER_URL} is not running. Start it with run.bat (or ./run.sh) and retry."}
            body = res.json()
            if res.status_code == 409:
                return {"synced": False, "already_running": True}
            if res.status_code == 429:
                return {"synced": False, "retry_after_sec": body.get("retry_after_sec")}
            if res.status_code != 202:
                return {"synced": False, "error": body.get("error", str(res.status_code))}

            async def get_snapshot() -> dict:
                return (await client.get("/api/crawl/status")).json()

            return await _wait_idle(get_snapshot)

    try:
        crawl.start_background("live", "mcp")
    except crawl.AlreadyRunning:
        return {"synced": False, "already_running": True}
    except crawl.Debounced as exc:
        return {"synced": False, "retry_after_sec": exc.retry_after_sec}

    async def get_snapshot() -> dict:
        return crawl.snapshot()

    return await _wait_idle(get_snapshot)


@mcp.tool()
@_logged
def list_events(target: str | None = None) -> dict:
    """Currently ongoing Korea Investment & Securities events. Call sync_now once before the first query of a conversation. target narrows to one customer group: '영업점' (branch), '뱅키스' (BanKIS online) or '연금' (pension). Groups come from the banner summary, so an unsummarized event has target_types null; such events stay in the result even with a target filter (their group is undecided) and are listed in pending_event_nums — call again after summarizing and only the matching ones remain. If pending_summaries > 0, finish the summaries before answering: get image_ids from list_pending_summaries and spawn one event-analyzer subagent per batch of two in parallel. The main session calls get_summary_tiles itself only on Claude Desktop, which has no subagents."""
    conn = db.connect()
    try:
        return queries.list_events(conn, target)
    finally:
        conn.close()


@mcp.tool()
@_logged
def events_on(date: str, target: str | None = None) -> dict:
    """Events whose application period covered a given date, ended ones included, as JSON. Call sync_now once before the first query of a conversation. date is YYYY-MM-DD. target narrows to '영업점' (branch), '뱅키스' (BanKIS online) or '연금' (pension). notice reports how many events are unsummarized and their numbers — if any, finish the summaries before answering: get image_ids from list_pending_summaries and spawn one event-analyzer subagent per batch of two in parallel (the main session calls get_summary_tiles itself only on Claude Desktop). Unsummarized events have target_types null and stay in the result even with a target filter."""
    conn = db.connect()
    try:
        events = queries.events_on(conn, date, target)
    except ValueError:
        return {"error": f"date must be YYYY-MM-DD, got {date!r}"}
    finally:
        conn.close()

    missing = [event["num"] for event in events if event["summary_status"] == "none"]
    if missing:
        notice = (
            f"{len(missing)} of {len(events)} events are unsummarized (event_nums: {', '.join(missing)})."
            " Get their image_ids with list_pending_summaries(event_nums=[...]), summarize first, then query again."
        )
    else:
        notice = f"All {len(events)} events are summarized."

    return {
        "date": date,
        "target": target,
        "notice": notice,
        "count": len(events),
        "pending_summaries": len(missing),
        "pending_event_nums": missing,
        "events": events,
    }


def _pending_rows(conn, event_nums: list[str] | None = None, ongoing_only: bool = False) -> list:
    sql = SUMMARY_CANDIDATE_SQL
    params: tuple = (_claim_cutoff(),)
    if event_nums:
        marks = ",".join("?" * len(event_nums))
        sql += f" AND i.event_num IN ({marks})"
        params += tuple(event_nums)
    if ongoing_only:
        sql += " AND e.state = 'ongoing'"
    return conn.execute(sql + SUMMARY_ORDER_SQL, params).fetchall()


def _batches(image_ids: list[int]) -> list[list[int]]:
    return [image_ids[i : i + BATCH_SIZE] for i in range(0, len(image_ids), BATCH_SIZE)]


def _pending_plan(rows) -> dict:
    """미요약 image_id를 서브에이전트 묶음으로 나눠 다음 행동까지 적어 준다."""
    ids = [row["id"] for row in rows]
    plan = {"pending": len(ids), "batches": _batches(ids)}
    if ids:
        plan["next"] = SUBAGENT_NEXT
    return plan


@mcp.tool()
@_logged
def list_pending_summaries(limit: int = 20, event_nums: list[str] | None = None) -> dict:
    """Unsummarized banner images (image_id, event_num, title) plus batches: the same image_ids pre-split into groups of two. Ongoing events first, then by period_end descending. event_nums restricts to those events. Spawn one event-analyzer subagent per batch, all in parallel (e.g. 5 ids → [[a,b],[c,d],[e]] → 3 subagents). The main session calls get_summary_tiles itself only where no subagents exist (Claude Desktop)."""
    conn = db.connect()
    try:
        rows = _pending_rows(conn, event_nums)
        return {
            **_pending_plan(rows),
            "items": [
                {"image_id": row["id"], "event_num": row["event_num"], "title": row["title"]}
                for row in rows[: max(1, limit)]
            ],
        }
    finally:
        conn.close()


@mcp.tool()
@_logged
def get_summary_tiles(
    limit: int = 1, event_nums: list[str] | None = None, image_id: int | None = None
) -> list[ContentBlock]:
    """[Tool for the event-analyzer subagent; the main session calls it directly only where no subagents exist.] Returns one crop of an unsummarized banner: the info-block region (y 1,200–3,600) just below the hero image, which holds the event period, the eligible customers and, when present, the target products/accounts and performance criteria. The text before the image carries image_id, event title, list period, list summary and the summary guide — read the crop and save a schema_version 2 JSON with save_summary. event_nums restricts to those events; image_id returns exactly that image (also an already summarized one, for re-summarizing). A 'no image to summarize' response means there is nothing left."""
    # limit은 1로 고정 취급한다 — 이미지 1장의 상단 크롭 1장이 한 호출이다(§7.4).
    conn = db.connect()
    try:
        cutoff = _claim_cutoff()
        if image_id is not None:
            row = conn.execute(SUMMARY_IMAGE_SQL, (image_id,)).fetchone()
        elif event_nums:
            marks = ",".join("?" * len(event_nums))
            rows = conn.execute(
                SUMMARY_CANDIDATE_SQL + f" AND i.event_num IN ({marks})",
                (cutoff, *event_nums),
            ).fetchall()
            row = min(rows, key=lambda r: event_nums.index(r["event_num"])) if rows else None
        else:
            row = conn.execute(
                SUMMARY_CANDIDATE_SQL + SUMMARY_ORDER_SQL + " LIMIT 1", (cutoff,)
            ).fetchone()

        if row is None:
            log.debug("no pending images")
            return [TextContent(type="text", text="no image to summarize")]

        y0, y1 = tiles.summary_crop(row["local_path"])
        conn.execute(
            "UPDATE event_images SET summary_claimed_at = ? WHERE id = ?", (_now(), row["id"])
        )
        conn.commit()
        log.debug("claimed image_id={}", row["id"])

        meta = {
            "image_id": row["id"],
            "event_num": row["event_num"],
            "title": row["title"],
            "list_summary": row["summary"],
            "list_period": {"start": row["period_start"], "end": row["period_end"]},
            "template": row["template"],
            "tiles": 1,
        }
        jpeg = tiles.render_tile(row["local_path"], y0, y1, SUMMARY_QUALITY)
        return [
            TextContent(
                type="text",
                text=f"{json.dumps(meta, ensure_ascii=False)}\n\n{SUMMARY_GUIDE}",
            ),
            TextContent(type="text", text=json.dumps({"y0": y0, "y1": y1}, ensure_ascii=False)),
            ImageContent(
                type="image", mimeType="image/jpeg", data=base64.b64encode(jpeg).decode()
            ),
        ]
    finally:
        conn.close()


@mcp.tool()
@_logged
def save_summary(image_id: int, summary: dict) -> dict:
    """Save a schema_version 2 summary. summary follows the guide from get_summary_tiles, same keys and order: {"analysis": what the image shows, "block_found": bool, "target": {"types": ["영업점"|"뱅키스"|"연금"...], "text": the eligible-customer wording as printed, "conditions": [str], "exclusions": [str]}, "criteria": {"text": str, "products": [str], "performance": str|null} | null}. When block_found is true target.text must not be empty; when false omit target and criteria. On validation failure you get errors — fix the JSON and call again. Once saved, the event's target_types show up in list_events and events_on."""
    try:
        parsed = SummaryV2.model_validate(summary)
    except ValidationError as exc:
        errors = [
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        ]
        log.warning("save_summary rejected image_id={} errors={}", image_id, errors[:3])
        return {"ok": False, "errors": errors}

    conn = db.connect()
    try:
        row = conn.execute("SELECT event_num FROM event_images WHERE id = ?", (image_id,)).fetchone()
        if row is None:
            log.warning("not found image_id={}", image_id)
            return {"ok": False, "errors": [f"image_id {image_id} not found"]}

        target_types = parsed.target.types
        conn.execute(
            "INSERT INTO image_summary (image_id, schema_version, json, target_types, summarized_at)"
            " VALUES (?, ?, ?, ?, ?) ON CONFLICT(image_id) DO UPDATE SET"
            " schema_version = excluded.schema_version, json = excluded.json,"
            " target_types = excluded.target_types, summarized_at = excluded.summarized_at",
            (
                image_id,
                SUMMARY_SCHEMA_VERSION,
                parsed.model_dump_json(),
                json.dumps(target_types, ensure_ascii=False),
                _now(),
            ),
        )
        conn.execute(
            "UPDATE event_images SET summary_claimed_at = NULL,"
            " status = CASE WHEN status = 'pending' THEN 'summarized' ELSE status END WHERE id = ?",
            (image_id,),
        )
        conn.commit()

        return {
            "ok": True,
            "image_id": image_id,
            "event_num": row["event_num"],
            "target_types": target_types,
            "pending_summaries": queries.pending_summaries(conn),
        }
    finally:
        conn.close()


@mcp.tool()
@_logged
def get_event(num: str) -> dict:
    """Full detail of one event: list fields plus the summary JSON (target, criteria). Use it for specific questions about conditions, caveats or amounts."""
    conn = db.connect()
    try:
        event = queries.event_detail(conn, num)
        return event if event is not None else {"error": "not found"}
    finally:
        conn.close()
