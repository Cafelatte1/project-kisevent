"""loguru 한 곳에서 콘솔·파일 sink를 잡고 표준 logging을 합류시킨다."""

import inspect
import logging
import os
import sys

from loguru import logger

from backend.core import paths

FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<7} | {extra[ctx]:<12} | {name}:{line} | {message}"
)

# 라이브러리 소음 조절
LIBRARY_LEVELS = {
    "httpx": "WARNING",
    "httpcore": "WARNING",
    "uvicorn.access": "DEBUG",
    "uvicorn": "INFO",
    "uvicorn.error": "INFO",
}
# access log는 INFO로 올라오지만 DEBUG로 낮춰 기본 INFO 콘솔·파일에서는 보이지 않게 한다
RECORD_LEVELS = {"uvicorn.access": "DEBUG"}
UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


class InterceptHandler(logging.Handler):
    """표준 logging 레코드를 loguru로 넘긴다."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = RECORD_LEVELS.get(record.name) or logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # emit() 자신부터 표준 logging 내부 프레임을 지나 실제 호출자까지 거슬러 올라간다
        frame, depth = inspect.currentframe(), 0
        while frame is not None and (depth == 0 or frame.f_code.co_filename == logging.__file__):
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def _force_utf8_streams() -> None:
    """cp949 콘솔에서 한글 로그가 깨지지 않게."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")


def setup(component: str) -> None:
    if sys.platform == "win32":
        _force_utf8_streams()

    paths.ensure_dirs()

    logger.remove()
    logger.configure(extra={"ctx": "-"})
    # stdout은 stdio MCP 프로토콜이라 콘솔 로그는 stderr로만 보낸다
    logger.add(
        sys.stderr,
        format=FORMAT,
        level=os.environ.get("KISEVENT_LOG_LEVEL", "INFO"),
        enqueue=True,
    )
    logger.add(
        paths.LOG_DIR / "app.log",
        format=FORMAT,
        level=os.environ.get("KISEVENT_FILE_LOG_LEVEL", "INFO"),
        rotation="10 MB",
        retention=5,
        encoding="utf-8",
        enqueue=True,
    )

    root = logging.getLogger()
    root.handlers = [InterceptHandler()]
    root.setLevel(0)
    for name, level in LIBRARY_LEVELS.items():
        logging.getLogger(name).setLevel(level)
    # uvicorn이 붙인 자체 핸들러를 떼어내 loguru로만 흐르게 한다
    for name in UVICORN_LOGGERS:
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True

    logger.bind(ctx="boot").info(
        "component={} log_dir={} data_dir={} platform={}",
        component,
        paths.LOG_DIR,
        paths.DATA_DIR,
        sys.platform,
    )
