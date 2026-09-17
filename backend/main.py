"""스케줄러 + REST + MCP를 한 프로세스로 띄운다."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from backend.api import routes
from backend.core import crawl, db, scheduler
from backend.core.logging import setup
from backend.core.scheduler import SCRAPE_INTERVAL_MIN
from backend.mcp.server import mcp

setup("server")

FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"
PORT = 4000

mcp_app = mcp.streamable_http_app(streamable_http_path="/mcp", stateless_http=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    boot = logger.bind(ctx="boot")

    conn = db.connect()
    added = db.init_schema(conn)
    if added:
        boot.info("schema ready added={}", added)
    else:
        boot.info("schema ready")
    cursor = conn.execute(
        "UPDATE scrape_runs SET finished_at = ?, error = 'interrupted' WHERE finished_at IS NULL",
        (datetime.now(timezone.utc).isoformat(),),
    )
    conn.commit()
    conn.close()
    if cursor.rowcount:
        boot.info("interrupted runs marked n={}", cursor.rowcount)
    else:
        boot.debug("interrupted runs marked n=0")

    running = scheduler.start()
    app.state.scheduler = running
    boot.info(
        "scheduler started interval_min={} next_run={}",
        SCRAPE_INTERVAL_MIN,
        crawl.snapshot()["next_run_at"],
    )
    boot.info("listening port={}", PORT)
    try:
        async with mcp.session_manager.run():
            yield
    finally:
        scheduler.stop(running)


app = FastAPI(lifespan=lifespan)


@app.exception_handler(Exception)
async def unhandled_error(request, exc: Exception):
    logger.bind(ctx="api").opt(exception=exc).error(
        "unhandled path={} error={}", request.url.path, exc
    )
    return JSONResponse(status_code=500, content={"error": "internal server error"})


app.include_router(routes.router)
# 루트 mount가 /mcp까지 삼키므로 mount 대신 경로 그대로(/mcp) 등록한다
app.router.routes.extend(mcp_app.routes)
app.mount("/images", StaticFiles(directory=db.IMAGE_DIR))
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True))


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_config=None)
