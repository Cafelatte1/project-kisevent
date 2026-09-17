"""대상 필터가 배너 요약(image_summary)에서 오고, 일자 조회가 기간·정렬을 지키는지 확인한다."""

import json

import pytest

from backend.core import db, queries
from backend.mcp import server


def _event(conn, num, title, start, end, state):
    conn.execute(
        "INSERT INTO events (num, title, summary, period_start, period_end, targets,"
        " first_seen_at, last_seen_at, state, seen_tab)"
        " VALUES (?, ?, NULL, ?, ?, '[]', '2026-09-01', '2026-09-17', ?, 'i')",
        (num, title, start, end, state),
    )


def _image(conn, num, target_types):
    cursor = conn.execute(
        "INSERT INTO event_images (event_num, url, local_path, sha256, status, created_at)"
        " VALUES (?, ?, ?, ?, ?, '2026-09-17')",
        (num, f"http://x/{num}.png", f"/tmp/{num}.png", num, "pending"),
    )
    image_id = cursor.lastrowid
    if target_types is None:
        return image_id

    summary = {
        "analysis": f"이벤트 {num} 정보 블록에서 대상과 기준을 읽었다.",
        "target": {"types": target_types, "text": "대상", "conditions": [], "exclusions": []},
        "criteria": {"text": "국내주식", "products": [], "performance": "1천만원 이상"},
        "block_found": True,
    }
    conn.execute(
        "INSERT INTO image_summary (image_id, schema_version, json, target_types, summarized_at)"
        " VALUES (?, 2, ?, ?, '2026-09-17')",
        (image_id, json.dumps(summary, ensure_ascii=False), json.dumps(target_types, ensure_ascii=False)),
    )
    conn.execute("UPDATE event_images SET status = 'summarized' WHERE id = ?", (image_id,))
    return image_id


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "events.db")
    connection = db.connect()
    db.init_schema(connection)

    _event(connection, "100", "뱅키스 이벤트", "2026.09.01", "2026.09.30", "ongoing")
    _image(connection, "100", ["뱅키스"])
    _event(connection, "200", "미요약 이벤트", "2026.09.10", "2026.10.31", "ongoing")
    _image(connection, "200", None)
    _event(connection, "300", "영업점·뱅키스 이벤트", "2026.08.01", "2026.09.20", "ended")
    _image(connection, "300", ["영업점", "뱅키스"])
    _event(connection, "400", "지난 영업점 이벤트", "2026.01.01", "2026.02.28", "ended")
    _image(connection, "400", ["영업점"])
    connection.commit()

    yield connection
    connection.close()


def test_list_events_target_keeps_unsummarized_and_counts_pending(conn):
    result = queries.list_events(conn, target="뱅키스")

    assert result["count"] == 2
    assert [event["num"] for event in result["events"]] == ["200", "100"]
    assert result["events"][1]["target_types"] == ["뱅키스"]
    assert result["events"][1]["summary"]["criteria"]["text"] == "국내주식"
    assert result["pending_summaries"] == 1 and result["pending_event_nums"] == ["200"]


def test_list_events_target_excludes_summarized_other_target(conn):
    result = queries.list_events(conn, target="영업점")

    assert [event["num"] for event in result["events"]] == ["200"]
    assert result["pending_summaries"] == 1 and result["pending_event_nums"] == ["200"]


def test_list_events_without_target_keeps_unsummarized(conn):
    result = queries.list_events(conn)

    assert [event["num"] for event in result["events"]] == ["200", "100"]
    unsummarized = next(event for event in result["events"] if event["num"] == "200")
    assert unsummarized["target_types"] is None
    assert unsummarized["summary"] is None
    assert unsummarized["summary_status"] == "none"
    assert result["pending_summaries"] == 1 and result["pending_event_nums"] == ["200"]


def test_events_on_orders_ongoing_first_then_period_end(conn):
    events = queries.events_on(conn, "2026-09-17")

    assert [event["num"] for event in events] == ["200", "100", "300"]
    assert [event["state"] for event in events] == ["ongoing", "ongoing", "ended"]


def test_events_on_target_matches_every_listed_type(conn):
    assert [event["num"] for event in queries.events_on(conn, "2026-09-17", "뱅키스")] == [
        "200",
        "100",
        "300",
    ]
    assert [event["num"] for event in queries.events_on(conn, "2026-09-17", "영업점")] == [
        "200",
        "300",
    ]


def test_events_on_excludes_dates_outside_period(conn):
    assert [event["num"] for event in queries.events_on(conn, "2026-02-01")] == ["400"]
    assert queries.events_on(conn, "2026-11-01") == []


def test_events_on_tool_returns_dict_with_notice_and_pending(conn):
    result = server.events_on("2026-09-17", "영업점")

    assert result["date"] == "2026-09-17" and result["target"] == "영업점"
    assert "1건 미요약" in result["notice"] and "200" in result["notice"]
    assert result["count"] == 2
    assert result["pending_summaries"] == 1 and result["pending_event_nums"] == ["200"]
    assert [event["num"] for event in result["events"]] == ["200", "300"]


def test_by_target_counts_unsummarized_as_unknown(conn):
    assert queries.by_target(conn) == {"영업점": 0, "뱅키스": 1, "연금": 0, "미상": 1}
