"""MCP sync_now: 서버 안에서는 게이트를 직접 타고, stdio에서는 서버 REST에 위임한다."""

import threading

import httpx
import pytest

from backend.core import crawl
from backend.mcp import server


@pytest.fixture(autouse=True)
def reset():
    original = crawl.RUNNER
    crawl.status = crawl.CrawlStatus()
    crawl._lock = threading.Lock()
    crawl._last_started_at = None
    crawl.RUNNER = lambda mode, on_progress: {"mode": mode}
    server.SYNC_VIA_HTTP = False
    yield
    crawl.RUNNER = original
    server.SYNC_VIA_HTTP = False


def test_local_sync_starts_then_debounces():
    assert server.sync_now() == {"started": True}
    second = server.sync_now()
    assert second["started"] is False and second["retry_after_sec"] >= 1


def test_local_sync_reports_running():
    gate = threading.Event()
    crawl.RUNNER = lambda mode, on_progress: gate.wait(3) or {"mode": mode}
    server.sync_now()
    assert server.sync_now() == {"started": False, "already_running": True}
    gate.set()


def test_http_sync_maps_status_codes(monkeypatch):
    server.SYNC_VIA_HTTP = True
    calls = []

    def fake_post(url, params, timeout):
        calls.append((url, params))
        status, body = responses.pop(0)
        return httpx.Response(status, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(server.httpx, "post", fake_post)
    responses = [(202, {"started": True}), (409, {"error": "already running"}), (429, {"retry_after_sec": 42})]

    assert server.sync_now() == {"started": True}
    assert server.sync_now() == {"started": False, "already_running": True}
    assert server.sync_now() == {"started": False, "retry_after_sec": 42}
    assert calls[0] == (f"{server.SERVER_URL}/api/scrape", {"mode": "live"})


def test_http_sync_when_server_down(monkeypatch):
    server.SYNC_VIA_HTTP = True

    def fake_post(url, params, timeout):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(server.httpx, "post", fake_post)
    result = server.sync_now()
    assert result["started"] is False and "꺼져" in result["error"]
