"""MCP sync_now: 서버 안에서는 게이트를 직접 타고 완료까지 기다리며, stdio에서는 서버 REST에 위임한다."""

import asyncio
import threading
import time

import httpx
import pytest

from backend.core import crawl
from backend.mcp import server

RealAsyncClient = httpx.AsyncClient


def _mock_client(handler):
    return lambda **kw: RealAsyncClient(transport=httpx.MockTransport(handler), **kw)


@pytest.fixture(autouse=True)
def reset():
    original = crawl.RUNNER
    crawl.status = crawl.CrawlStatus()
    crawl._lock = threading.Lock()
    crawl._last_started_at = None
    crawl.RUNNER = lambda mode, on_progress: {"mode": mode, "events": 3, "new": 1, "updated": 0}
    server.SYNC_VIA_HTTP = False
    yield
    crawl.RUNNER = original
    server.SYNC_VIA_HTTP = False


def test_local_sync_waits_and_returns_counts_then_debounces():
    first = asyncio.run(server.sync_now())
    assert first["synced"] is True and first["new"] == 1 and first["events"] == 3
    assert crawl.snapshot()["state"] == "idle"
    second = asyncio.run(server.sync_now())
    assert second["synced"] is False and second["retry_after_sec"] >= 1


def test_local_sync_reports_running():
    gate = threading.Event()
    crawl.RUNNER = lambda mode, on_progress: gate.wait(3) or {"mode": mode}
    crawl.start_background("live", trigger="manual")
    assert asyncio.run(server.sync_now()) == {"synced": False, "already_running": True}
    gate.set()
    # 다음 테스트가 락을 갈아끼우기 전에 백그라운드 스레드가 끝나야 한다
    for _ in range(300):
        if crawl.snapshot()["state"] == "idle":
            break
        time.sleep(0.01)


def test_local_sync_reports_run_error():
    def failing(mode, on_progress):
        raise RuntimeError("boom")

    crawl.RUNNER = failing
    result = asyncio.run(server.sync_now())
    assert result["synced"] is False and "boom" in result["error"]


def test_http_sync_delegates_and_polls(monkeypatch):
    server.SYNC_VIA_HTTP = True
    statuses = [
        {"state": "running"},
        {"state": "idle", "last_error": None, "last_result": {"events": 3, "new": 2, "updated": 0}, "last_finished_at": "t"},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/scrape":
            assert request.url.params["mode"] == "live"
            return httpx.Response(202, json={"started": True})
        return httpx.Response(200, json=statuses.pop(0))

    monkeypatch.setattr(server.httpx, "AsyncClient", _mock_client(handler))
    result = asyncio.run(server.sync_now())
    assert result["synced"] is True and result["new"] == 2 and not statuses


def test_http_sync_maps_gate_codes(monkeypatch):
    server.SYNC_VIA_HTTP = True
    responses = [(409, {"error": "already running"}), (429, {"retry_after_sec": 42})]

    def handler(request):
        status, body = responses.pop(0)
        return httpx.Response(status, json=body)

    monkeypatch.setattr(server.httpx, "AsyncClient", _mock_client(handler))
    assert asyncio.run(server.sync_now()) == {"synced": False, "already_running": True}
    assert asyncio.run(server.sync_now()) == {"synced": False, "retry_after_sec": 42}


def test_http_sync_when_server_down(monkeypatch):
    server.SYNC_VIA_HTTP = True

    def handler(request):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(server.httpx, "AsyncClient", _mock_client(handler))
    result = asyncio.run(server.sync_now())
    assert result["synced"] is False and "꺼져" in result["error"]


def test_batches_split_by_two():
    assert server._batches([1, 2, 3, 4, 5]) == [[1, 2], [3, 4], [5]]
    assert server._batches([]) == []
