"""라이브/백필 두 모드가 같은 테이블에서 state를 어떻게 다루는지. HTTP는 대체한다."""

import pytest

from backend.core import db, scraper

DETAIL_HTML = '<div id="ifrmContent"><p>이미지 없는 상세</p></div>'


class _FakeResponse:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self) -> None:
        pass


class _FakeClient:
    detail_urls: list[str] = []

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url, params=None):
        _FakeClient.detail_urls.append(url)
        return _FakeResponse(DETAIL_HTML)


def _item(num: str, end: str = "2026.09.30") -> dict:
    return {
        "num": num,
        "title": f"이벤트 {num}",
        "summary": None,
        "period_start": "2026.09.01",
        "period_end": end,
        "thumbnail_url": None,
    }


@pytest.fixture
def run(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "events.db")
    monkeypatch.setattr(scraper.httpx, "Client", _FakeClient)
    seen_gubun: list[str] = []

    def do(mode: str, items: list[dict]) -> dict:
        by_code = {"00": items}

        def fake_fetch(client, code, gubun, limit=None, on_page=None):
            seen_gubun.append(gubun)
            return by_code.get(code, []), 1

        monkeypatch.setattr(scraper, "fetch_list_all", fake_fetch)
        _FakeClient.detail_urls = []
        return scraper.run_once(mode)

    do.gubun = seen_gubun
    return do


def _states(conn) -> dict:
    return {row["num"]: row["state"] for row in conn.execute("SELECT num, state FROM events")}


def test_live_ends_events_that_disappeared(run):
    run("live", [_item("1"), _item("2")])
    conn = db.connect()
    assert _states(conn) == {"1": "ongoing", "2": "ongoing"}
    conn.close()

    result = run("live", [_item("1")])
    assert result["mode"] == "live"
    assert result["updated"] == 1  # 사라진 이벤트의 ended 전환도 갱신으로 집계
    conn = db.connect()
    assert _states(conn) == {"1": "ongoing", "2": "ended"}
    conn.close()
    assert run.gubun == ["i", "i"]


def test_backfill_keeps_ongoing_and_adds_ended(run):
    run("live", [_item("1")])
    run("backfill", [_item("1"), _item("9", end="2025.12.31")])

    conn = db.connect()
    assert _states(conn) == {"1": "ongoing", "9": "ended"}
    tabs = {row["num"]: row["seen_tab"] for row in conn.execute("SELECT num, seen_tab FROM events")}
    assert tabs == {"1": "i", "9": "t"}
    conn.close()

    assert run.gubun[-1:] == ["t"]
    # 이미 상세를 받은 1은 건너뛰고, 새로 들어온 9만 지난 이벤트 탭으로 연다
    assert len(_FakeClient.detail_urls) == 1
    assert "num=9" in _FakeClient.detail_urls[0]
    assert "gubun=t" in _FakeClient.detail_urls[0]
    assert "CUSTGUBUN=00" in _FakeClient.detail_urls[0]
