# CLAUDE.md

When the user says "셋팅해줘" (set it up — serving PC, non-developer), follow `SETUP.md` from top to bottom: install uv, `uv sync`, register the Task Scheduler job, connect Claude Code/Desktop and run the final verification. The agent does all of it.

## Project

KIS Event: a local, single-user service that scrapes Korea Investment & Securities (한국투자증권) event notices (branch and BanKIS customers) on demand into SQLite, and lets Claude Desktop / Claude Code answer "지금 영업점 고객대상 이벤트가 뭐가 있어?" over MCP.
Almost all event content sits inside banner images 7k–30k px tall. There is one analysis, **summary v2**: one crop of the banner's info-block region (y 1,200–3,600) goes out over MCP and the agent stores `analysis (what the image shows) → block_found → target (every applicable group among 영업점·뱅키스·연금) → criteria (products, accounts, performance and other conditions)` in `image_summary`. The application period is not extracted (the list has it) and nothing below 3,600 px (benefit details, caveats) is covered. The 영업점/뱅키스 distinction comes only from this summary, never from the list tabs (pension events appear on both tabs, which would bias them); an unsummarized event is "미상" (unknown). Agents finish pending summaries before answering; in Claude Code they hand `.claude/agents/event-analyzer.md` image_ids in batches of two and run the batches in parallel. Site structure, template classes, crop range and schema rationale live in `docs/event-page-research.md` (§6 — blank-row tiles and full transcription — is the retired v1 record).
Scraping is plain GET + HTML parsing, no login or JS; only the `CUSTGUBUN=00` (all customers) tab is read (00 = 영업점 ∪ 뱅키스, nothing exists only in 00). The list walks `currentPage` until an empty page (`MAX_PAGES=20`); old templates without `#ifrmContent` fall back to the `<!--b:s-->…<!--b:e-->` block. An image is re-downloaded and re-summarized only when its URL or sha256 changes.
Collection never runs on its own (on demand). Two modes: `live` (called by MCP `sync_now`, ongoing tab `gubun=i`) marks events missing from this run as `state='ended'`; `backfill` (past-events tab `gubun=t`, `BACKFILL_LIMIT` default 100, 0 = everything, dashboard button only and optional) always starts at page 1 and reads until the count is reached, skipping detail/image fetches for known numbers and never demoting `ongoing`. The human UI shows three pages, but direct GET returns everything back to 2016 (1,250 events as of 2026-09-17). Ended events need `gubun=t` on the detail page for the image to render (`events.seen_tab`). `crawl.py` is the single run gate: 409 while a run is in progress, 429 within 60 s of the last start.

## Layout

- `backend/` — Python 3.12, uv. One process serves REST + MCP on `127.0.0.1:4000`
  - `core/` — `scraper.py` (list/detail parsing, image download, live/backfill), `db.py` (sqlite3 WAL, schema and migrations), `tiles.py` (fixed crop + JPEG render for the summary), `crawl.py` (run gate and status), `queries.py` (shared queries for REST and MCP)
  - `api/` — FastAPI REST (`/api/*`) and static serving of `frontend/`
  - `mcp/` — `server.py` defines the tools: collection `sync_now` (live only; waits for the run and returns new/updated plus the pending image_id batches; agents call it once before the first query — backfill is dashboard-only), queries `list_events` · `events_on` (per-date JSON with an unsummarized notice) · `get_event`, summaries `list_pending_summaries` · `get_summary_tiles` · `save_summary`. `schema.py` holds the v2 pydantic models and the agent guide. Exposed as Streamable HTTP at `/mcp`; `stdio.py` runs the same server over stdio (reads the same DB, and its `sync_now` delegates to the server's `POST /api/scrape` so the run gate is shared)
  - `main.py` — app assembly and startup
- `.claude/agents/event-analyzer.md` — Sonnet subagent that summarizes up to two banners per run (tools: `get_summary_tiles`, `save_summary` only). The MCP server must be registered as `kis-event` for the tool names to match
- `AGENTS.md` / `.codex/agents/event-analyzer.toml` — the same flow and subagent for Codex (GPT); the agent file is copied to `~/.codex/agents/`
- `frontend/index.html` — single-file status board, no build: "n분 전 수집 - 결과" header, warnings for a failed last run or an unreachable server, tiles (ongoing, unsummarized, per group), the event table (target, period, summary) with a detail panel, and the runs that changed something. The only button is "지난 이벤트 100건 수집" (backfill); live sync happens through MCP `sync_now`
- `data/` — `events.db`, `images/` (original banners). Not committed; movable with `KISEVENT_DATA_DIR`
- Logging — `backend/core/logging.py` (loguru). File `%LOCALAPPDATA%\kisevent\logs\app.log` (macOS `~/Library/Application Support/kisevent/logs/`), 10 MB rotation × 5. Format `time | level | ctx | module:line | message`, ctx ∈ live/backfill/mcp/api/boot/tiles. Four tables: `events`, `event_images` (status: pending|summarized|failed|superseded), `image_summary`, `scrape_runs`. uvicorn and httpx logging is routed here; httpx requests and access logs are DEBUG. Env vars `KISEVENT_LOG_DIR`, `KISEVENT_LOG_LEVEL`, `KISEVENT_FILE_LOG_LEVEL`, `KISEVENT_APP_DIR`; collection: `BACKFILL_LIMIT` (100)
- `docs/event-page-research.md` — site measurements and design decisions (Korean)
- `SETUP.md` — install procedure for the serving PC (Windows, non-developer), executed by the agent (Korean)
- `.mcp.json` — lets Claude Code pick up `kis-event` (HTTP `/mcp`) automatically in this folder
- `install.bat` — Windows one-shot installer, standalone: when not run inside a clone it installs git (winget) and clones into `%USERPROFILE%\project-kisevent`; then installs uv if missing, `uv sync`, registers the `KISEvent` logon task and starts it, merges the `kis-event` stdio entry into `claude_desktop_config.json` (existing entries kept, `.bak` written), waits for `/api/health`
- `update.bat` — Windows updater: `git fetch`/`pull --ff-only`, `uv sync`, restart the server through the `KISEvent` task (falls back to `run-hidden.vbs`), waits for `/api/health`
- `run.bat` / `run-hidden.vbs` — Windows: kill whatever holds port 4000 and start the server (the vbs runs it without a console, for Task Scheduler). `run.sh` — the same for macOS/Linux

## Commands (from the repo root)

- Environment: `uv sync`
- Server: `./run.sh` (macOS) / `run.bat` (Windows) / `uv run python -m backend.main` — all on `127.0.0.1:4000`. Starting the server does not collect anything
- One-off scrape: `uv run python -m backend.core.scraper --mode live|backfill` (with the server up, use the dashboard button or `POST /api/scrape?mode=`)
- Tests: `uv run pytest`
- Claude Desktop: add `{"command": "uv", "args": ["--directory", "<repo path>", "run", "python", "-m", "backend.mcp.stdio"]}` to `claude_desktop_config.json` (Desktop may not see PATH, so an absolute path to `uv` is safer — see SETUP.md). If it accepts HTTP connectors, `http://localhost:4000/mcp` also works
- Claude Code: `claude mcp add --transport http kis-event http://localhost:4000/mcp`

## FronyBoard

This project is tracked by FronyBoard (project key: KIS).
Manage tasks through the FronyBoard MCP tools, following the FronyBoard server instructions.
Task tags: `frontend` / `backend` / `infra` / `docs` for where the work lands, plus
`design` or `test` for what kind it is. Reuse these rather than coining a synonym.
