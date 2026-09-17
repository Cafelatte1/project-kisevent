"""스케줄러 + REST + MCP를 한 프로세스로 띄운다."""

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.api import routes
from backend.core import db, scheduler
from backend.mcp.server import mcp

logging.basicConfig(level=logging.INFO)

FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"

mcp_app = mcp.streamable_http_app(streamable_http_path="/mcp", stateless_http=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = db.connect()
    db.init_schema(conn)
    conn.execute(
        "UPDATE scrape_runs SET finished_at = ?, error = 'interrupted' WHERE finished_at IS NULL",
        (datetime.now(timezone.utc).isoformat(),),
    )
    conn.commit()
    conn.close()

    running = scheduler.start()
    app.state.scheduler = running
    try:
        async with mcp.session_manager.run():
            yield
    finally:
        scheduler.stop(running)


app = FastAPI(lifespan=lifespan)

app.include_router(routes.router)
# 루트 mount가 /mcp까지 삼키므로 mount 대신 경로 그대로(/mcp) 등록한다
app.router.routes.extend(mcp_app.routes)
app.mount("/images", StaticFiles(directory=db.IMAGE_DIR))
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True))
