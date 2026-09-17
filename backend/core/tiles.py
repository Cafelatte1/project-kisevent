"""배너 이미지를 여백 행에서 타일로 자른다(docs/event-page-research.md §6.6)."""

import io

import numpy as np
from PIL import Image

TARGET = 2000
WINDOW = 400
MAX_TILE = 2400
BAND = 20
BLANK_THRESHOLD = 2.0
FALLBACK_OVERLAP = 150
SUMMARY_Y0 = 1200
SUMMARY_Y1 = 3600

Image.MAX_IMAGE_PIXELS = None


def _row_scores(image_path: str) -> np.ndarray:
    with Image.open(image_path) as image:
        gray = np.asarray(image.convert("L"), dtype=np.float32)

    scores = gray.std(axis=1)
    scores[1:] += np.abs(gray[1:] - gray[:-1]).mean(axis=1)
    return scores


def _band_means(scores: np.ndarray) -> np.ndarray:
    """인덱스 s에서 시작하는 BAND폭 띠의 평균 score."""
    cumulative = np.concatenate(([0.0], np.cumsum(scores, dtype=np.float64)))
    return (cumulative[BAND:] - cumulative[:-BAND]) / BAND


def plan_tiles(image_path: str) -> list[tuple[int, int, int]]:
    """(y0, y1, overlap) 목록. 목표 높이 근처에서 가장 잉크가 없는 띠의 중앙을 자른다."""
    scores = _row_scores(image_path)
    height = len(scores)
    bands = _band_means(scores)

    tiles: list[tuple[int, int, int]] = []
    y = 0
    overlap = 0

    while height - y > MAX_TILE:
        low = y + TARGET - WINDOW
        window = bands[low : y + TARGET + WINDOW - BAND + 1]
        best = int(np.argmin(window))

        if window[best] <= BLANK_THRESHOLD:
            cut = low + best + BAND // 2
            tiles.append((y, cut, overlap))
            y, overlap = cut, 0
        else:
            cut = y + TARGET
            tiles.append((y, cut, overlap))
            y, overlap = cut - FALLBACK_OVERLAP, FALLBACK_OVERLAP

    tiles.append((y, height, overlap))
    return tiles


def summary_crop(image_path: str) -> tuple[int, int]:
    """요약용 고정 크롭(y0, y1). 정보 블록은 배너 상단 1,200~3,600px에 있다(§7.4)."""
    with Image.open(image_path) as image:
        height = image.height

    return min(SUMMARY_Y0, max(0, height - MAX_TILE)), min(SUMMARY_Y1, height)


def render_tile(image_path: str, y0: int, y1: int, quality: int = 80) -> bytes:
    with Image.open(image_path) as image:
        tile = image.convert("RGB").crop((0, y0, image.width, y1))

    buffer = io.BytesIO()
    tile.save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()


def ensure_tiles(conn, image_id: int) -> None:
    """image_tiles에 행이 없으면 계획해서 넣는다."""
    existing = conn.execute(
        "SELECT COUNT(*) FROM image_tiles WHERE image_id = ?", (image_id,)
    ).fetchone()[0]
    if existing:
        return

    row = conn.execute("SELECT local_path FROM event_images WHERE id = ?", (image_id,)).fetchone()
    tiles = plan_tiles(row["local_path"])

    conn.executemany(
        "INSERT INTO image_tiles (image_id, idx, y0, y1, overlap) VALUES (?, ?, ?, ?, ?)",
        [(image_id, idx, y0, y1, overlap) for idx, (y0, y1, overlap) in enumerate(tiles)],
    )
    conn.execute("UPDATE event_images SET tile_count = ? WHERE id = ?", (len(tiles), image_id))
    conn.commit()
