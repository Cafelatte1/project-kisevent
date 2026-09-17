"""배너 이미지에서 요약용 구간을 잘라 낸다(docs/event-page-research.md §7.4)."""

import io
from contextlib import contextmanager
from pathlib import Path

from loguru import logger
from PIL import Image

SUMMARY_HEIGHT = 2400
SUMMARY_Y0 = 1200
SUMMARY_Y1 = 3600

Image.MAX_IMAGE_PIXELS = None

log = logger.bind(ctx="tiles")


@contextmanager
def _open(image_path: str):
    try:
        image = Image.open(image_path)
    except Exception as exc:
        log.warning("image open failed path={} error={}", image_path, exc)
        raise
    with image:
        yield image


def summary_crop(image_path: str) -> tuple[int, int]:
    """요약용 고정 크롭(y0, y1). 정보 블록은 배너 상단 1,200~3,600px에 있다(§7.4)."""
    with _open(image_path) as image:
        height = image.height

    y0, y1 = min(SUMMARY_Y0, max(0, height - SUMMARY_HEIGHT)), min(SUMMARY_Y1, height)
    log.debug("summary crop image={} y0={} y1={}", Path(image_path).name, y0, y1)
    return y0, y1


def render_tile(image_path: str, y0: int, y1: int, quality: int = 80) -> bytes:
    with _open(image_path) as image:
        tile = image.convert("RGB").crop((0, y0, image.width, y1))

    buffer = io.BytesIO()
    tile.save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()
