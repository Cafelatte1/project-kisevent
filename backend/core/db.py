"""sqlite 연결과 스키마."""

import sqlite3

from loguru import logger

from backend.core.paths import DATA_DIR, DB_PATH, IMAGE_DIR, ensure_dirs

__all__ = ["DATA_DIR", "DB_PATH", "IMAGE_DIR", "connect", "init_schema"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  num TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  summary TEXT,
  period_start TEXT,
  period_end TEXT,
  thumbnail_url TEXT,
  targets TEXT NOT NULL,
  template TEXT,
  detail_title TEXT,
  actions TEXT,
  legacy_text TEXT,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'ongoing',
  seen_tab TEXT NOT NULL DEFAULT 'i'
);

CREATE TABLE IF NOT EXISTS event_images (
  id INTEGER PRIMARY KEY,
  event_num TEXT NOT NULL REFERENCES events(num),
  url TEXT NOT NULL,
  local_path TEXT NOT NULL,
  width INTEGER,
  height INTEGER,
  bytes INTEGER,
  sha256 TEXT NOT NULL,
  tile_count INTEGER,
  status TEXT NOT NULL DEFAULT 'pending',
  summary_claimed_at TEXT,
  created_at TEXT NOT NULL,
  UNIQUE(event_num, url)
);

CREATE TABLE IF NOT EXISTS image_summary (
  image_id INTEGER PRIMARY KEY REFERENCES event_images(id),
  schema_version INTEGER NOT NULL,
  json TEXT NOT NULL,
  target_types TEXT NOT NULL,
  summarized_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scrape_runs (
  id INTEGER PRIMARY KEY,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  new_count INTEGER,
  updated_count INTEGER,
  image_count INTEGER,
  error TEXT,
  mode TEXT NOT NULL DEFAULT 'live',
  pages INTEGER,
  events_seen INTEGER
);
"""

DROPPED_TABLES = ("image_tiles", "image_analysis")

# 전사·구조화(v1) 어휘로 남아 있는 status를 요약(v2) 어휘로 옮긴다.
STATUS_MIGRATIONS = (
    "UPDATE event_images SET status = 'pending' WHERE status IN ('transcribing', 'transcribed')",
    "UPDATE event_images SET status = CASE WHEN EXISTS"
    " (SELECT 1 FROM image_summary s WHERE s.image_id = event_images.id)"
    " THEN 'summarized' ELSE 'pending' END WHERE status = 'analyzed'",
)

ADDED_COLUMNS = {
    "event_images": {
        "summary_claimed_at": "TEXT",
    },
    "events": {
        "state": "TEXT NOT NULL DEFAULT 'ongoing'",
        "seen_tab": "TEXT NOT NULL DEFAULT 'i'",
    },
    "scrape_runs": {
        "mode": "TEXT NOT NULL DEFAULT 'live'",
        "pages": "INTEGER",
        "events_seen": "INTEGER",
    },
}


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _drop_legacy_tables(conn: sqlite3.Connection) -> None:
    for table in DROPPED_TABLES:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
        ).fetchone()
        if exists:
            conn.execute(f"DROP TABLE {table}")
            logger.info("table dropped table={}", table)


def init_schema(conn: sqlite3.Connection) -> list[str]:
    """마이그레이션으로 추가된 컬럼 이름(table.column) 목록을 돌려준다."""
    ensure_dirs()
    conn.executescript(SCHEMA)
    _drop_legacy_tables(conn)
    for statement in STATUS_MIGRATIONS:
        conn.execute(statement)

    added: list[str] = []
    for table, columns in ADDED_COLUMNS.items():
        existing = _columns(conn, table)
        for name, decl in columns.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
                added.append(f"{table}.{name}")
                logger.info("column added table={} column={}", table, name)
                if table == "events" and name == "state" and "active" in existing:
                    conn.execute(
                        "UPDATE events SET state = CASE WHEN active = 1 THEN 'ongoing' ELSE 'ended' END"
                    )

    if not added:
        logger.debug("schema unchanged")

    conn.commit()
    return added
