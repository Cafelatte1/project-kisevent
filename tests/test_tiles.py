"""여백 행 절단이 실제 배너와 합성 이미지에서 성립하는지 확인한다."""

import numpy as np
import pytest
from PIL import Image

from backend.core import db
from backend.core.tiles import BAND, BLANK_THRESHOLD, MAX_TILE, _row_scores, plan_tiles


def _largest_banner():
    images = sorted(db.IMAGE_DIR.glob("*.*"), key=lambda path: path.stat().st_size)
    return images[-1] if images else None


def test_plan_tiles_on_real_banner():
    banner = _largest_banner()
    if banner is None:
        pytest.skip("data/images 에 배너가 없다")

    tiles = plan_tiles(str(banner))
    scores = _row_scores(str(banner))

    for y0, y1, overlap in tiles[:-1]:
        assert 1600 <= y1 - y0 <= MAX_TILE
        assert overlap == 0
        band = scores[y1 - BAND // 2 : y1 + BAND // 2]
        assert band.mean() < BLANK_THRESHOLD

    assert tiles[0][0] == 0
    assert tiles[-1][1] == len(scores)


def test_cut_lands_on_blank_band(tmp_path):
    pixels = np.full((5000, 1120), 255, dtype=np.uint8)
    for y in range(0, 5000, 20):  # 글자 대신 10px 검은 띠를 20px 간격으로
        pixels[y : y + 10, :] = 0
    pixels[1960:2060, :] = 255  # 여백은 2000·4000 근처에만
    pixels[3960:4060, :] = 255

    path = tmp_path / "synthetic.png"
    Image.fromarray(pixels, mode="L").save(path)

    tiles = plan_tiles(str(path))

    assert len(tiles) == 3
    assert 1960 <= tiles[0][1] <= 2060
    assert 3960 <= tiles[1][1] <= 4060
    assert all(overlap == 0 for _, _, overlap in tiles)
