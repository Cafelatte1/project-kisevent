"""요약용 고정 크롭이 실제 배너와 짧은 이미지에서 성립하는지 확인한다."""

import numpy as np
import pytest
from PIL import Image

from backend.core import db
from backend.core.tiles import SUMMARY_Y0, SUMMARY_Y1, summary_crop


def _largest_banner():
    images = sorted(db.IMAGE_DIR.glob("*.*"), key=lambda path: path.stat().st_size)
    return images[-1] if images else None


def test_summary_crop_on_real_banner():
    banner = _largest_banner()
    if banner is None:
        pytest.skip("data/images 에 배너가 없다")

    assert summary_crop(str(banner)) == (SUMMARY_Y0, SUMMARY_Y1)


def test_summary_crop_on_short_images(tmp_path):
    def _save(height: int):
        path = tmp_path / f"short_{height}.png"
        Image.fromarray(np.full((height, 1120), 255, dtype=np.uint8), mode="L").save(path)
        return str(path)

    assert summary_crop(_save(3000)) == (600, 3000)
    assert summary_crop(_save(2000)) == (0, 2000)
