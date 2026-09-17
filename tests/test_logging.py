"""loguru sink 설정: 파일 기록 포맷, ctx 바인딩, 표준 logging 합류."""

import importlib
import logging as std_logging

import pytest
from loguru import logger


@pytest.fixture
def log_file(tmp_path, monkeypatch):
    monkeypatch.setenv("KISEVENT_LOG_DIR", str(tmp_path / "logs"))

    from backend.core import logging as app_logging
    from backend.core import paths

    importlib.reload(paths)
    importlib.reload(app_logging)
    app_logging.setup("test")

    yield tmp_path / "logs" / "app.log"

    logger.remove()
    importlib.reload(paths)
    importlib.reload(app_logging)


def _read(path):
    logger.complete()
    return path.read_text(encoding="utf-8")


def test_file_sink_created_with_format(log_file):
    assert log_file.exists()

    logger.info("hello")

    assert f"| INFO    | -            | {__name__}:" in _read(log_file)
    assert "hello" in _read(log_file)


def test_bound_ctx_lands_in_column(log_file):
    logger.bind(ctx="live").info("run start mode=live")

    assert "| INFO    | live         | " in _read(log_file)


def test_standard_logging_is_intercepted(log_file):
    std_logging.getLogger("x").warning("from stdlib")

    content = _read(log_file)
    assert "from stdlib" in content
    assert "| WARNING | " in content
