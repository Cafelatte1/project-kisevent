"""sqlite 연결과 스키마."""

import sqlite3
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
DB_PATH = DATA_DIR / "events.db"
IMAGE_DIR = DATA_DIR / "images"

DATA_DIR.mkdir(parents=True, exist_ok=True)
IMAGE_DIR.mkdir(parents=True, exist_ok=True)

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
  active INTEGER NOT NULL DEFAULT 1
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
  created_at TEXT NOT NULL,
  UNIQUE(event_num, url)
);

CREATE TABLE IF NOT EXISTS image_tiles (
  image_id INTEGER NOT NULL REFERENCES event_images(id),
  idx INTEGER NOT NULL,
  y0 INTEGER NOT NULL,
  y1 INTEGER NOT NULL,
  overlap INTEGER NOT NULL DEFAULT 0,
  text TEXT,
  transcribed_at TEXT,
  PRIMARY KEY(image_id, idx)
);

CREATE TABLE IF NOT EXISTS image_analysis (
  image_id INTEGER PRIMARY KEY REFERENCES event_images(id),
  schema_version INTEGER NOT NULL,
  summary TEXT NOT NULL,
  json TEXT NOT NULL,
  analyzed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scrape_runs (
  id INTEGER PRIMARY KEY,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  new_count INTEGER,
  updated_count INTEGER,
  image_count INTEGER,
  error TEXT
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()
