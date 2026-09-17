"""Claude Desktop이 붙는 MCP tool 정의."""

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

from backend.core import db, queries, tiles
from backend.mcp.schema import SUMMARY_GUIDE, SUMMARY_SCHEMA_VERSION, SummaryV2

INSTRUCTIONS = (
    "한국투자증권 이벤트 수집·요약 서버. 이벤트 내용은 배너 이미지 안에 있어, 질문에 답하기 전에 관련 이벤트의"
    " 배너가 요약돼 있어야 한다. 흐름: list_events 또는 events_on으로 대상 이벤트를 고른다 → 미요약이 있으면"
    " list_pending_summaries로 image_id를 받는다 → Claude Code처럼 서브에이전트를 쓸 수 있으면 image_id마다"
    " banner-summarizer를 병렬로 띄우고, 아니면 get_summary_tiles → save_summary를 직접 순서대로 한다 →"
    " 다시 조회해 답한다."
)

mcp = MCPServer("kis-event", instructions=INSTRUCTIONS)

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

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        started = time.monotonic()
        try:
            return func(*args, **kwargs)
        finally:
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

    return wrapper


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _claim_cutoff() -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=CLAIM_TIMEOUT_MIN)).isoformat()


@mcp.tool()
@_logged
def list_events(target: str | None = None) -> dict:
    """현재 진행 중인 한국투자증권 이벤트 목록. target에 '영업점'·'뱅키스'·'연금'을 주면 그 대상만 돌려준다. 대상은 배너 이미지 요약에서 얻으므로 요약 전 이벤트는 target_types가 null이다. target을 줘도 요약 전 이벤트(target_types null)는 대상이 확정되지 않았으므로 결과에 포함되며 pending_event_nums에 잡힌다 — 요약을 마친 뒤 다시 호출하면 그 대상만 남는다. 응답의 pending_summaries가 0보다 크면 아직 요약되지 않은 배너가 있다는 뜻이니, 사용자 질문에 답하기 전에 list_pending_summaries로 image_id를 받아 요약을 먼저 끝내라(Claude Code면 image_id마다 banner-summarizer 서브에이전트를 병렬로, 아니면 get_summary_tiles → save_summary를 직접)."""
    conn = db.connect()
    try:
        return queries.list_events(conn, target)
    finally:
        conn.close()


@mcp.tool()
@_logged
def events_on(date: str, target: str | None = None) -> dict:
    """특정 일자에 신청 기간이 걸려 있던 이벤트를 JSON으로 돌려준다(종료 이벤트 포함). date는 YYYY-MM-DD. target에 '영업점'·'뱅키스'·'연금'을 주면 그 대상만 돌려준다. notice에 요약되지 않은 이벤트 수와 번호가 있다 — 미요약 건이 있으면 답하기 전에 list_pending_summaries로 image_id를 받아 요약을 먼저 끝내라(Claude Code면 image_id마다 banner-summarizer 서브에이전트를 병렬로, 아니면 get_summary_tiles → save_summary를 직접). 요약 전 이벤트는 target_types가 null이며, target을 줘도 대상이 확정되지 않았으므로 결과에 포함된다."""
    conn = db.connect()
    try:
        events = queries.events_on(conn, date, target)
    except ValueError:
        return {"error": f"date는 YYYY-MM-DD 형식이어야 합니다: {date!r}"}
    finally:
        conn.close()

    missing = [event["num"] for event in events if event["summary_status"] == "none"]
    if missing:
        notice = (
            f"※ {len(events)}건 중 {len(missing)}건 미요약 (번호: {', '.join(missing)})."
            " list_pending_summaries(event_nums=[...])로 image_id를 받아 먼저 요약한 뒤 다시 조회하세요."
        )
    else:
        notice = f"※ {len(events)}건 모두 요약 완료."

    return {
        "date": date,
        "target": target,
        "notice": notice,
        "count": len(events),
        "pending_summaries": len(missing),
        "pending_event_nums": missing,
        "events": events,
    }


@mcp.tool()
@_logged
def list_pending_summaries(limit: int = 20, event_nums: list[str] | None = None) -> dict:
    """요약되지 않은 배너 이미지 목록(image_id, event_num, title). 진행중 이벤트가 먼저, 그다음 종료일 내림차순. event_nums를 주면 그 이벤트들만. Claude Code라면 이 목록의 image_id마다 banner-summarizer 서브에이전트를 하나씩 병렬로 띄워라(건당 이미지 1장). 서브에이전트를 쓸 수 없는 환경이면 get_summary_tiles → save_summary를 image_id별로 직접 순서대로 수행한다."""
    conn = db.connect()
    try:
        sql = SUMMARY_CANDIDATE_SQL
        params: tuple = (_claim_cutoff(),)
        if event_nums:
            marks = ",".join("?" * len(event_nums))
            sql += f" AND i.event_num IN ({marks})"
            params += tuple(event_nums)

        rows = conn.execute(sql + SUMMARY_ORDER_SQL, params).fetchall()
        return {
            "pending": len(rows),
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
    """미요약 배너 1장의 배너 상단 정보 블록 구간(y 1,200~3,600) 1장을 돌려준다. 정보 블록(이벤트 기간·참여대상, 있으면 대상 상품/계좌·실적 인정)은 히어로 이미지 바로 아래에 있다. 타일 앞의 텍스트에 image_id·이벤트 제목·목록 기간·목록 요약·요약 안내가 있으니 타일을 모두 읽고 schema_version 2 JSON을 save_summary로 저장하라. event_nums를 주면 그 이벤트들만, image_id를 주면 그 이미지만 돌려준다. 응답이 '요약할 이미지가 없습니다'면 끝난 것이다. image_id를 주면 이미 요약된 이미지도 다시 돌려준다(재요약)."""
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
            return [TextContent(type="text", text="요약할 이미지가 없습니다")]

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
    """schema_version 2 요약 저장. 검증 실패면 errors를 돌려주니 고쳐서 다시 호출하라. 저장되면 그 이벤트의 대상(target_types)이 list_events·events_on에 반영된다."""
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
            return {"ok": False, "errors": [f"image_id {image_id}를 찾을 수 없습니다"]}

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
    """이벤트 한 건의 상세: 목록 정보, 요약 JSON(대상·기준). 조건·유의사항·금액처럼 구체적인 질문에 답할 때 쓴다."""
    conn = db.connect()
    try:
        event = queries.event_detail(conn, num)
        return event if event is not None else {"error": "not found"}
    finally:
        conn.close()
