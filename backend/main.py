"""스케줄러 + REST + MCP를 한 프로세스로 띄운다."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.core import db, scheduler
from backend.mcp.server import PENDING_SQL, mcp

logging.basicConfig(level=logging.INFO)

mcp_app = mcp.streamable_http_app(streamable_http_path="/mcp", stateless_http=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = db.connect()
    db.init_schema(conn)
    conn.close()

    running = scheduler.start()
    try:
        async with mcp.session_manager.run():
            yield
    finally:
        scheduler.stop(running)


app = FastAPI(lifespan=lifespan)


@app.get("/api/health")
def health() -> dict:
    conn = db.connect()
    try:
        last_run = conn.execute("SELECT * FROM scrape_runs ORDER BY id DESC LIMIT 1").fetchone()
        return {
            "ok": True,
            "last_run": dict(last_run) if last_run is not None else None,
            "pending_images": conn.execute(PENDING_SQL).fetchone()[0],
        }
    finally:
        conn.close()


app.mount("/", mcp_app)
