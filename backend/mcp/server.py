"""Claude Desktop이 붙는 MCP tool 정의."""

import base64
import json
from datetime import datetime, timezone

from mcp.server.mcpserver import MCPServer
from mcp.types import ContentBlock, ImageContent, TextContent
from pydantic import ValidationError

from backend.core import db, tiles
from backend.mcp.schema import SCHEMA_GUIDE, SCHEMA_VERSION, AnalysisV1

mcp = MCPServer("kis-event")

PENDING_SQL = "SELECT COUNT(*) FROM event_images WHERE status NOT IN ('analyzed', 'superseded', 'failed')"
LATEST_IMAGE_SQL = (
    "SELECT id, status FROM event_images WHERE event_num = ? AND status != 'superseded'"
    " ORDER BY id DESC LIMIT 1"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pending_images(conn) -> int:
    return conn.execute(PENDING_SQL).fetchone()[0]


def _transcript(conn, image_id: int) -> str:
    rows = conn.execute(
        "SELECT text FROM image_tiles WHERE image_id = ? ORDER BY idx", (image_id,)
    ).fetchall()
    return "\n\n".join(row["text"] or "" for row in rows)


@mcp.tool()
def list_events(target: str | None = None) -> dict:
    """현재 진행 중인 한국투자증권 이벤트 목록. target에 '영업점' 또는 '뱅키스'를 주면 그 고객대상만 돌려준다. 응답의 pending_images가 0보다 크면 아직 전사·구조화되지 않은 배너 이미지가 있다는 뜻이다. 이벤트 내용은 거의 전부 이미지 안에 있으므로, 사용자 질문에 답하기 전에 get_pending_tiles → save_tile_text → (이미지의 타일이 모두 저장되면) get_transcript → save_analysis 순서로 분석을 먼저 끝내라. 각 이벤트의 analysis_summary가 있으면 그것이 이미지에서 추출한 요약이고, 없으면 아직 분석 전이다."""
    conn = db.connect()
    try:
        events = []
        for row in conn.execute("SELECT * FROM events WHERE active = 1 ORDER BY num DESC"):
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
            "pending_images": _pending_images(conn),
            "count": len(events),
            "events": events,
        }
    finally:
        conn.close()


@mcp.tool()
def get_pending_tiles(limit: int = 2) -> list[ContentBlock]:
    """미분석 배너 이미지의 다음 타일을 최대 limit장 돌려준다(타일당 1120×약2000px, 위에서 아래 순서). 각 타일 앞의 텍스트에 image_id, tile_idx, tile_total, overlap이 있다. 타일을 보고 보이는 글자를 그대로 전사해 save_tile_text로 저장하라. overlap이 150인 타일은 상단 150px가 이전 타일과 겹치므로 중복되는 줄은 빼고 전사한다. 한 이미지의 타일이 모두 저장되면 그 이미지는 transcribed 상태가 되고 get_transcript로 넘어간다. 응답이 '분석할 이미지가 없습니다'면 모든 이미지가 처리된 것이다."""
    limit = max(1, min(3, limit))
    conn = db.connect()
    try:
        row = conn.execute(
            "SELECT i.id FROM event_images i JOIN image_tiles t ON t.image_id = i.id"
            " WHERE i.status = 'transcribing' AND t.text IS NULL ORDER BY i.id LIMIT 1"
        ).fetchone()
        if row is None:
            row = conn.execute(
                "SELECT id FROM event_images WHERE status = 'pending' ORDER BY id LIMIT 1"
            ).fetchone()
        if row is None:
            return [TextContent(type="text", text="분석할 이미지가 없습니다")]

        image_id = row["id"]
        tiles.ensure_tiles(conn, image_id)
        conn.execute("UPDATE event_images SET status = 'transcribing' WHERE id = ?", (image_id,))
        conn.commit()

        image = conn.execute(
            "SELECT i.local_path, i.tile_count, i.event_num, e.title FROM event_images i"
            " JOIN events e ON e.num = i.event_num WHERE i.id = ?",
            (image_id,),
        ).fetchone()

        contents: list[ContentBlock] = []
        for tile in conn.execute(
            "SELECT idx, y0, y1, overlap FROM image_tiles WHERE image_id = ? AND text IS NULL"
            " ORDER BY idx LIMIT ?",
            (image_id, limit),
        ).fetchall():
            meta = {
                "image_id": image_id,
                "event_num": image["event_num"],
                "event_title": image["title"],
                "tile_idx": tile["idx"],
                "tile_total": image["tile_count"],
                "y0": tile["y0"],
                "y1": tile["y1"],
                "overlap": tile["overlap"],
            }
            jpeg = tiles.render_tile(image["local_path"], tile["y0"], tile["y1"])
            contents.append(TextContent(type="text", text=json.dumps(meta, ensure_ascii=False)))
            contents.append(
                ImageContent(
                    type="image", mimeType="image/jpeg", data=base64.b64encode(jpeg).decode()
                )
            )

        return contents
    finally:
        conn.close()


@mcp.tool()
def save_tile_text(image_id: int, tile_idx: int, text: str) -> dict:
    """타일 전사 결과 저장. text는 타일에 보이는 글자를 순서대로 옮긴 원문이다(요약·해석 금지, 표는 행마다 셀을 ' | '로 구분). 글자가 전혀 없는 장식 타일은 빈 문자열로 저장한다. 응답의 remaining_tiles가 0이면 get_transcript(image_id)로 넘어가라."""
    conn = db.connect()
    try:
        cursor = conn.execute(
            "UPDATE image_tiles SET text = ?, transcribed_at = ? WHERE image_id = ? AND idx = ?",
            (text, _now(), image_id, tile_idx),
        )
        if cursor.rowcount == 0:
            return {"error": f"타일을 찾을 수 없습니다: image_id={image_id}, tile_idx={tile_idx}"}

        remaining = conn.execute(
            "SELECT COUNT(*) FROM image_tiles WHERE image_id = ? AND text IS NULL", (image_id,)
        ).fetchone()[0]
        if remaining == 0:
            conn.execute("UPDATE event_images SET status = 'transcribed' WHERE id = ?", (image_id,))
        conn.commit()

        status = conn.execute(
            "SELECT status FROM event_images WHERE id = ?", (image_id,)
        ).fetchone()["status"]
        return {"image_id": image_id, "remaining_tiles": remaining, "status": status}
    finally:
        conn.close()


@mcp.tool()
def get_transcript(image_id: int) -> dict:
    """이미지 전체 전사문과 목록·HTML에서 얻은 메타데이터, 구조화 안내를 돌려준다. 이것을 읽고 schema_version 1 JSON으로 구조화한 뒤 save_analysis로 저장하라."""
    conn = db.connect()
    try:
        row = conn.execute(
            "SELECT i.event_num, e.title, e.targets, e.period_start, e.period_end, e.summary,"
            " e.actions, e.detail_title FROM event_images i JOIN events e ON e.num = i.event_num"
            " WHERE i.id = ?",
            (image_id,),
        ).fetchone()
        if row is None:
            return {"error": "not found"}

        result = {
            "image_id": image_id,
            "event_num": row["event_num"],
            "title": row["title"],
            "list_targets": json.loads(row["targets"]),
            "list_period": {"start": row["period_start"], "end": row["period_end"]},
            "list_summary": row["summary"],
            "list_actions": json.loads(row["actions"] or "[]"),
            "detail_title": row["detail_title"],
            "transcript": _transcript(conn, image_id),
            "schema_guide": SCHEMA_GUIDE,
        }

        missing = conn.execute(
            "SELECT COUNT(*) FROM image_tiles WHERE image_id = ? AND text IS NULL", (image_id,)
        ).fetchone()[0]
        if missing:
            result["warning"] = f"타일 {missing}개가 아직 전사되지 않았습니다"

        return result
    finally:
        conn.close()


@mcp.tool()
def save_analysis(image_id: int, analysis: dict, summary: str) -> dict:
    """구조화 결과 저장. analysis는 schema_version 1 JSON, summary는 대상+핵심 혜택+신청 기간을 담은 200자 이내 한 문장(list_events에 그대로 실린다). 검증에 실패하면 오류 내용을 돌려주니 고쳐서 다시 호출하라."""
    try:
        parsed = AnalysisV1.model_validate(analysis)
    except ValidationError as exc:
        return {
            "ok": False,
            "errors": [
                f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
                for error in exc.errors()
            ],
        }

    if len(summary) > 200:
        return {"ok": False, "errors": [f"summary가 200자를 넘습니다({len(summary)}자)"]}

    conn = db.connect()
    try:
        row = conn.execute("SELECT event_num FROM event_images WHERE id = ?", (image_id,)).fetchone()
        if row is None:
            return {"ok": False, "errors": [f"image_id {image_id}를 찾을 수 없습니다"]}

        conn.execute(
            "INSERT INTO image_analysis (image_id, schema_version, summary, json, analyzed_at)"
            " VALUES (?, ?, ?, ?, ?) ON CONFLICT(image_id) DO UPDATE SET"
            " schema_version = excluded.schema_version, summary = excluded.summary,"
            " json = excluded.json, analyzed_at = excluded.analyzed_at",
            (image_id, SCHEMA_VERSION, summary, parsed.model_dump_json(), _now()),
        )
        conn.execute("UPDATE event_images SET status = 'analyzed' WHERE id = ?", (image_id,))
        conn.commit()

        return {
            "ok": True,
            "image_id": image_id,
            "event_num": row["event_num"],
            "pending_images": _pending_images(conn),
        }
    finally:
        conn.close()


@mcp.tool()
def get_event(num: str) -> dict:
    """이벤트 한 건의 상세: 목록 정보, 구조화된 분석 JSON, 전체 전사문. 조건·유의사항·금액처럼 구체적인 질문에 답할 때 쓴다."""
    conn = db.connect()
    try:
        row = conn.execute("SELECT * FROM events WHERE num = ?", (num,)).fetchone()
        if row is None:
            return {"error": "not found"}

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
            "analysis": json.loads(analysis["json"]) if analysis is not None else None,
            "summary": analysis["summary"] if analysis is not None else None,
            "transcript": _transcript(conn, image["id"]),
        }
        return event
    finally:
        conn.close()
