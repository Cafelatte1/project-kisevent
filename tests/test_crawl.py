"""실행 게이트: 동시 실행 차단과 수동 debounce."""

import threading
import time

import pytest

from backend.core import crawl


@pytest.fixture(autouse=True)
def reset_crawl():
    original = crawl.RUNNER
    crawl.status = crawl.CrawlStatus()
    crawl._lock = threading.Lock()
    crawl._last_started_at = None
    yield
    crawl.RUNNER = original


def _wait_idle(timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if crawl.snapshot()["state"] == "idle":
            return
        time.sleep(0.01)
    raise AssertionError("크롤링이 끝나지 않았다")


def test_second_run_while_running_raises():
    gate = threading.Event()

    def runner(mode, on_progress):
        on_progress(2, 7)
        gate.wait(3)
        return {"mode": mode}

    crawl.RUNNER = runner
    crawl.start_background("live", trigger="manual")

    while crawl.snapshot()["state"] != "running":
        time.sleep(0.01)
    status = crawl.snapshot()
    assert status["mode"] == "live"
    assert (status["page"], status["events_seen"]) == (2, 7)

    with pytest.raises(crawl.AlreadyRunning):
        crawl.start_background("backfill", trigger="manual")

    gate.set()
    _wait_idle()
    assert crawl.snapshot()["last_result"] == {"mode": "live"}


def test_manual_run_within_window_is_debounced():
    crawl.RUNNER = lambda mode, on_progress: {"mode": mode}
    crawl.run("live", trigger="manual")

    with pytest.raises(crawl.Debounced) as exc:
        crawl.run("live", trigger="manual")
    assert 0 < exc.value.retry_after_sec <= crawl.DEBOUNCE_SEC
    assert crawl.snapshot()["state"] == "idle"


def test_failure_is_recorded_not_raised():
    def runner(mode, on_progress):
        raise RuntimeError("boom")

    crawl.RUNNER = runner
    crawl.run("live", trigger="manual")

    status = crawl.snapshot()
    assert status["state"] == "idle"
    assert status["last_error"] == "boom"
