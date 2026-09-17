"""크롤링 실행 게이트와 진행 상태. 스케줄러·REST가 함께 쓴다."""

import math
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from loguru import logger

from backend.core import scraper

DEBOUNCE_SEC = 60

# 테스트에서 갈아끼울 수 있게 간접 참조한다
RUNNER = scraper.run_once


class AlreadyRunning(Exception):
    """이미 다른 크롤링이 돌고 있다."""


class Debounced(Exception):
    """직전 실행이 너무 최근이다."""

    def __init__(self, retry_after_sec: int):
        super().__init__(f"{retry_after_sec}초 뒤에 다시 시도하세요")
        self.retry_after_sec = retry_after_sec


@dataclass
class CrawlStatus:
    state: str = "idle"  # idle | running
    mode: str | None = None
    started_at: str | None = None
    page: int = 0
    pages_hint: int | None = None
    events_seen: int = 0
    last_finished_at: str | None = None
    last_mode: str | None = None
    last_error: str | None = None
    last_result: dict | None = None
    next_run_at: str | None = None


status = CrawlStatus()
_lock = threading.Lock()
_state_lock = threading.Lock()
_last_started_at: float | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def snapshot() -> dict:
    with _state_lock:
        return asdict(status)


def set_next_run(value: str | None) -> None:
    with _state_lock:
        status.next_run_at = value


def _begin(mode: str, trigger: str) -> None:
    """호출 스레드에서 게이트를 통과시킨다. 통과하면 락을 쥔 채로 돌아온다."""
    global _last_started_at

    log = logger.bind(ctx=mode)

    if not _lock.acquire(blocking=False):
        log.info("run rejected reason=already_running")
        raise AlreadyRunning()

    try:
        # 스케줄러만 debounce를 건너뛴다(대시보드 manual·MCP mcp 모두 적용)
        if trigger != "scheduler" and _last_started_at is not None:
            elapsed = time.monotonic() - _last_started_at
            if elapsed < DEBOUNCE_SEC:
                retry_after = max(1, math.ceil(DEBOUNCE_SEC - elapsed))
                log.info("run rejected reason=debounced retry_after={}", retry_after)
                raise Debounced(retry_after)

        _last_started_at = time.monotonic()
        with _state_lock:
            status.state = "running"
            status.mode = mode
            status.started_at = _now()
            status.page = 0
            status.events_seen = 0
            status.last_error = None
    except Exception:
        _lock.release()
        raise

    log.info("run start mode={} trigger={}", mode, trigger)


def _on_progress(page: int, events_seen: int) -> None:
    with _state_lock:
        status.page = page
        status.events_seen = events_seen


def _execute(mode: str) -> dict:
    log = logger.bind(ctx=mode)
    started = time.monotonic()

    try:
        result = RUNNER(mode, _on_progress)
        error = None
        log.info(
            "run done run_id={} events={} new={} updated={} images={} failed={} pages={} elapsed={}s",
            result.get("run_id"),
            result.get("events"),
            result.get("new"),
            result.get("updated"),
            result.get("images"),
            len(result.get("failed") or []),
            result.get("pages"),
            round(time.monotonic() - started, 1),
        )
    except Exception as exc:
        log.exception("run failed mode={} error={}", mode, exc)
        result = {"error": str(exc)}
        error = str(exc)

    with _state_lock:
        status.state = "idle"
        status.mode = None
        status.started_at = None
        status.last_finished_at = _now()
        status.last_mode = mode
        status.last_error = error
        status.last_result = None if error else result
    _lock.release()
    return result


def run(mode: str, trigger: str = "scheduler") -> dict:
    _begin(mode, trigger)
    return _execute(mode)


def start_background(mode: str, trigger: str = "manual") -> None:
    _begin(mode, trigger)
    threading.Thread(target=_execute, args=(mode,), daemon=True).start()
