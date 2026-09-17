"""한국투자증권 이벤트 목록·상세 스크랩과 sqlite 저장."""

import hashlib
import json
import logging
import re
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from pathlib import PurePosixPath
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from PIL import Image

from backend.core import db

BASE_URL = "https://securities.koreainvestment.com/main/customer/notice/Event.jsp"
HEADERS = {"User-Agent": "Mozilla/5.0"}
TABS = {"01": "영업점", "02": "뱅키스"}
# 진행중 탭(i)과 지난 이벤트 탭(t)
LIST_TAB = {"live": "i", "backfill": "t"}
BACKFILL_DAYS = 365
MAX_PAGES = 60

Image.MAX_IMAGE_PIXELS = None

logger = logging.getLogger(__name__)

_NUM_RE = re.compile(r"doView\('(\d+)'\)")
_BODY_RE = re.compile(r"<!--b:s-->(.*?)<!--b:e-->", re.DOTALL)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(text: str) -> str:
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def parse_list(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    events = []

    for box in soup.select(".event_thum_box"):
        match = _NUM_RE.search(box.get("href") or "")
        if not match:
            continue

        date_el = box.select_one(".date .letter_0")
        period = _clean(date_el.get_text()).replace("\n", " ") if date_el else ""
        start, _, end = period.partition("~")
        title_el = box.select_one(".title")
        summary_el = box.select_one(".con")
        img_el = box.select_one(".event_img img")

        events.append(
            {
                "num": match.group(1),
                "title": _clean(title_el.get_text()) if title_el else "",
                "summary": _clean(summary_el.get_text()) if summary_el else None,
                "period_start": start.strip() or None,
                "period_end": end.strip() or None,
                "thumbnail_url": urljoin(BASE_URL, img_el["src"]) if img_el and img_el.get("src") else None,
            }
        )

    return events


def _period_end(item: dict) -> date | None:
    value = (item.get("period_end") or "").strip()
    try:
        return datetime.strptime(value, "%Y.%m.%d").date()
    except ValueError:
        return None


def collect_pages(
    fetch_page: Callable[[int], list[dict]],
    stop_before: date | None = None,
    on_page: Callable[[int, list[dict]], None] | None = None,
) -> tuple[list[dict], int]:
    """빈 페이지까지 순회한다. 정렬이 엄격하지 않으므로 한 페이지의 '최대' 종료일이
    stop_before보다 이전일 때만 그 페이지까지 포함하고 멈춘다."""
    events: list[dict] = []
    pages = 0

    for page in range(1, MAX_PAGES + 1):
        items = fetch_page(page)
        if not items:
            break

        pages += 1
        events.extend(items)
        if on_page is not None:
            on_page(page, items)

        if stop_before is not None:
            ends = [end for end in (_period_end(item) for item in items) if end is not None]
            if ends and max(ends) < stop_before:
                break

    return events, pages


def fetch_list_all(
    client: httpx.Client,
    code: str,
    gubun: str,
    stop_before: date | None = None,
    on_page: Callable[[str, int, list[dict]], None] | None = None,
) -> tuple[list[dict], int]:
    def fetch_page(page: int) -> list[dict]:
        response = client.get(
            BASE_URL,
            params={"gubun": gubun, "cmd": "TF04gb010001", "currentPage": page, "CUSTGUBUN": code},
        )
        response.raise_for_status()
        return parse_list(response.text)

    report = None if on_page is None else (lambda page, items: on_page(code, page, items))
    return collect_pages(fetch_page, stop_before, report)


def detail_url(num: str, code: str, gubun: str) -> str:
    return f"{BASE_URL}?gubun={gubun}&cmd=TF04gb010002&num={num}&currentPage=1&CUSTGUBUN={code}"


def parse_detail(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    container = soup.select_one("#ifrmContent")

    if container is not None:
        if container.select_one("form[name=eventForm]") is None:
            template = "A"
        elif container.select_one("input[type=checkbox], iframe, map area") is not None:
            template = "B"
        else:
            template = "C"
    else:
        body = _BODY_RE.search(html)
        if body is None:
            return {"template": None, "image_url": None, "detail_title": None, "actions": [], "legacy_text": None}
        container = BeautifulSoup(body.group(1), "lxml")
        template = "D"

    img = container.select_one(".events_1 img") or container.select_one("img")
    image_url = urljoin(BASE_URL, img["src"]) if img is not None and img.get("src") else None

    title_el = container.select_one("title")
    if title_el is not None and _clean(title_el.get_text()):
        detail_title = _clean(title_el.get_text())
    elif img is not None and (img.get("alt") or "").strip():
        detail_title = img["alt"].strip()
    else:
        detail_title = None

    actions = [area["alt"].strip() for area in container.select("map area") if (area.get("alt") or "").strip()]

    legacy_text = None
    if template == "D":
        parts = [
            _clean(div.get_text())
            for div in container.find_all("div")
            if "clip:rect" in (div.get("style") or "") or "clip: rect" in (div.get("style") or "")
        ]
        legacy_text = "\n".join(part for part in parts if part) or None

    return {
        "template": template,
        "image_url": image_url,
        "detail_title": detail_title,
        "actions": actions,
        "legacy_text": legacy_text,
    }


def download_image(client: httpx.Client, url: str) -> tuple[bytes, str]:
    response = client.get(url)
    response.raise_for_status()
    return response.content, hashlib.sha256(response.content).hexdigest()


def _merge_lists(lists: dict[str, list[dict]]) -> list[dict]:
    merged: dict[str, dict] = {}

    for code, events in lists.items():
        for event in events:
            existing = merged.get(event["num"])
            if existing:
                existing["codes"].append(code)
            else:
                merged[event["num"]] = {**event, "codes": [code]}

    return list(merged.values())


def _upsert_event(conn, event: dict, now: str) -> str:
    targets = json.dumps([TABS[code] for code in event["codes"]], ensure_ascii=False)
    row = conn.execute(
        "SELECT title, summary, period_start, period_end, thumbnail_url FROM events WHERE num = ?",
        (event["num"],),
    ).fetchone()

    if row is None:
        conn.execute(
            "INSERT INTO events (num, title, summary, period_start, period_end, thumbnail_url, targets,"
            " first_seen_at, last_seen_at, state, seen_tab) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ongoing', 'i')",
            (
                event["num"],
                event["title"],
                event["summary"],
                event["period_start"],
                event["period_end"],
                event["thumbnail_url"],
                targets,
                now,
                now,
            ),
        )
        return "new"

    changed = any(
        row[field] != event[field]
        for field in ("title", "summary", "period_start", "period_end", "thumbnail_url")
    )
    conn.execute(
        "UPDATE events SET title = ?, summary = ?, period_start = ?, period_end = ?, thumbnail_url = ?,"
        " targets = ?, last_seen_at = ?, state = 'ongoing', seen_tab = 'i' WHERE num = ?",
        (
            event["title"],
            event["summary"],
            event["period_start"],
            event["period_end"],
            event["thumbnail_url"],
            targets,
            now,
            event["num"],
        ),
    )
    return "updated" if changed else "same"


def _mark_ended(conn, seen: set[str]) -> None:
    sql = "UPDATE events SET state = 'ended' WHERE state = 'ongoing'"
    if seen:
        sql += f" AND num NOT IN ({','.join('?' * len(seen))})"
    conn.execute(sql, tuple(seen))


def _backfill_event(conn, event: dict, now: str) -> str:
    """지난 이벤트 탭에서 본 이벤트. 이미 있으면 targets만 합치고 state는 내리지 않는다."""
    labels = [TABS[code] for code in event["codes"]]
    row = conn.execute("SELECT targets FROM events WHERE num = ?", (event["num"],)).fetchone()

    if row is None:
        conn.execute(
            "INSERT INTO events (num, title, summary, period_start, period_end, thumbnail_url, targets,"
            " first_seen_at, last_seen_at, state, seen_tab) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ended', 't')",
            (
                event["num"],
                event["title"],
                event["summary"],
                event["period_start"],
                event["period_end"],
                event["thumbnail_url"],
                json.dumps(labels, ensure_ascii=False),
                now,
                now,
            ),
        )
        return "new"

    merged = set(json.loads(row["targets"])) | set(labels)
    targets = json.dumps([label for label in TABS.values() if label in merged], ensure_ascii=False)
    conn.execute(
        "UPDATE events SET targets = ?, last_seen_at = ? WHERE num = ?", (targets, now, event["num"])
    )
    return "updated" if targets != row["targets"] else "same"


def _needs_detail(conn, num: str, template: str | None) -> bool:
    if template is not None:
        return False
    return conn.execute(
        "SELECT 1 FROM event_images WHERE event_num = ? LIMIT 1", (num,)
    ).fetchone() is None


def _store_image(conn, client: httpx.Client, num: str, url: str, now: str) -> bool:
    exists = conn.execute(
        "SELECT 1 FROM event_images WHERE event_num = ? AND url = ?", (num, url)
    ).fetchone()
    if exists:
        return False

    content, digest = download_image(client, url)
    ext = PurePosixPath(urlparse(url).path).suffix.lower() or ".png"
    path = db.IMAGE_DIR / f"{num}_{digest[:8]}{ext}"
    path.write_bytes(content)

    with Image.open(path) as image:
        width, height = image.size

    conn.execute(
        "INSERT INTO event_images (event_num, url, local_path, width, height, bytes, sha256, status, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
        (num, url, str(path), width, height, len(content), digest, now),
    )
    conn.execute(
        "UPDATE event_images SET status = 'superseded' WHERE event_num = ? AND url != ?", (num, url)
    )
    return True


def run_once(mode: str = "live", on_progress: Callable[[int, int], None] | None = None) -> dict:
    if mode not in LIST_TAB:
        raise ValueError(f"알 수 없는 mode: {mode}")

    conn = db.connect()
    db.init_schema(conn)

    started_at = _now()
    cursor = conn.execute(
        "INSERT INTO scrape_runs (started_at, mode) VALUES (?, ?)", (started_at, mode)
    )
    run_id = cursor.lastrowid
    conn.commit()

    new_count = 0
    updated_count = 0
    image_count = 0
    pages = 0
    merged: list[dict] = []
    failed: list[str] = []

    gubun = LIST_TAB[mode]
    stop_before = date.today() - timedelta(days=BACKFILL_DAYS) if mode == "backfill" else None

    try:
        with httpx.Client(headers=HEADERS, timeout=30.0, follow_redirects=True) as client:
            progress = {"pages": 0, "events": 0}

            def report(code: str, page: int, items: list[dict]) -> None:
                progress["pages"] += 1
                progress["events"] += len(items)
                if on_progress is not None:
                    on_progress(progress["pages"], progress["events"])

            lists = {}
            for code in TABS:
                lists[code], read = fetch_list_all(client, code, gubun, stop_before, report)
                pages += read
            merged = _merge_lists(lists)
            logger.info("%s 목록 %d건 수집(%d페이지)", mode, len(merged), pages)

            now = _now()
            for event in merged:
                result = (
                    _upsert_event(conn, event, now)
                    if mode == "live"
                    else _backfill_event(conn, event, now)
                )
                if result == "new":
                    new_count += 1
                elif result == "updated":
                    updated_count += 1
            if mode == "live":
                _mark_ended(conn, {event["num"] for event in merged})
            conn.commit()

            for event in merged:
                num = event["num"]
                row = conn.execute(
                    "SELECT seen_tab, template FROM events WHERE num = ?", (num,)
                ).fetchone()
                if mode == "backfill" and not _needs_detail(conn, num, row["template"]):
                    continue

                try:
                    response = client.get(detail_url(num, event["codes"][0], row["seen_tab"]))
                    response.raise_for_status()
                    detail = parse_detail(response.text)
                except Exception:
                    logger.exception("이벤트 %s 상세 조회 실패", num)
                    failed.append(num)
                    continue

                conn.execute(
                    "UPDATE events SET template = ?, detail_title = ?, actions = ?, legacy_text = ? WHERE num = ?",
                    (
                        detail["template"],
                        detail["detail_title"],
                        json.dumps(detail["actions"], ensure_ascii=False),
                        detail["legacy_text"],
                        num,
                    ),
                )

                if detail["image_url"]:
                    try:
                        if _store_image(conn, client, num, detail["image_url"], _now()):
                            image_count += 1
                    except Exception:
                        logger.exception("이벤트 %s 이미지 저장 실패", num)
                        failed.append(num)

                conn.commit()
    except Exception as exc:
        conn.execute(
            "UPDATE scrape_runs SET finished_at = ?, error = ? WHERE id = ?", (_now(), str(exc), run_id)
        )
        conn.commit()
        conn.close()
        raise

    conn.execute(
        "UPDATE scrape_runs SET finished_at = ?, new_count = ?, updated_count = ?, image_count = ?,"
        " pages = ?, events_seen = ? WHERE id = ?",
        (_now(), new_count, updated_count, image_count, pages, len(merged), run_id),
    )
    conn.commit()
    conn.close()

    return {
        "run_id": run_id,
        "mode": mode,
        "events": len(merged),
        "pages": pages,
        "new": new_count,
        "updated": updated_count,
        "images": image_count,
        "failed": failed,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=sorted(LIST_TAB), default="live")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    print(json.dumps(run_once(args.mode), ensure_ascii=False))
