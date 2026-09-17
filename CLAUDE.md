# CLAUDE.md

사용자가 "셋팅해줘"라고 하면(서빙 PC, 비개발자) `SETUP.md`를 처음부터 끝까지 그대로 수행한다 — uv 설치, `uv sync`, 작업 스케줄러 등록, Claude Code/Desktop 연결, 최종 검증까지 에이전트가 한다.

## 프로젝트

KIS Event: 한국투자증권 이벤트 공고(영업점·뱅키스 고객대상)를 15분 주기로 스크랩해 SQLite에 쌓고, Claude Desktop이 MCP로 붙어 "지금 영업점 고객대상 이벤트가 뭐가 있어?"에 답하는 로컬 개인용 서비스.
이벤트 내용은 거의 전부 세로 7k~30k px 배너 이미지 안에 있다. 분석은 **요약 v2** 하나다: 배너 상단 정보 블록 구간(y 1,200~3,600) 1장을 MCP로 넘기면 에이전트가 `analysis(추론) → target(영업점·뱅키스·연금 중 해당 전부) → criteria(상품·계좌·실적 등 기타)`를 `image_summary`에 저장한다. 신청 기간은 목록에 있으므로 뽑지 않고, 3,600px 아래 내용(혜택 상세·유의사항)은 다루지 않는다. 영업점/뱅키스 구분은 목록 탭이 아니라 이 요약에서만 나오며(연금 이벤트가 두 탭에 같이 실리는 편향 때문), 요약 전 이벤트는 "미상"이다. 에이전트는 미요약 이미지가 있으면 답하기 전에 요약을 먼저 마치고, Claude Code에서는 `.claude/agents/banner-summarizer.md`를 image_id마다 병렬로 띄운다. 사이트 구조·템플릿 분류·크롭 범위·스키마의 근거는 `docs/event-page-research.md`를 따른다(§6의 여백 행 타일·전체 전사는 폐기된 v1 기록이다).
스크랩은 로그인·JS 실행 없는 GET + HTML 파싱이며, 고객 탭은 `CUSTGUBUN=00`(전체) 하나만 읽는다(00 = 영업점∪뱅키스, 00에만 있는 이벤트 없음). 목록은 `currentPage`를 빈 페이지까지 순회(`MAX_PAGES=20`)하고 `#ifrmContent`가 없는 구형 템플릿은 `<!--b:s-->…<!--b:e-->` 구간으로 폴백한다. 이미지는 URL 또는 sha256이 바뀔 때만 다시 받고 다시 요약한다.
동기화는 두 모드다. `live`(15분, 진행중 탭 `gubun=i`)는 이번에 안 보인 이벤트를 `state='ended'`로 내리고, `backfill`(지난 이벤트 탭 `gubun=t`, `BACKFILL_LIMIT` 기본 100건·0이면 전체, 첫 기동 시 자동 1회·이후 수동)은 매번 1페이지부터 건수가 찰 때까지 돌되 이미 아는 번호는 상세·이미지를 건너뛰고 `ongoing`을 내리지 않는다. 사람이 보는 화면은 3페이지지만 직접 GET은 2016년까지 전부 나온다(2026-09-17 기준 1,250건). 종료 이벤트 상세는 `gubun=t`로 열어야 이미지가 나온다(`events.seen_tab`). 실행 게이트는 `crawl.py` 하나다: 동시 실행 409, 수동 요청은 마지막 실행 시작 60초 이내면 429.

## 디렉토리 구조

- `backend/` — Python 3.12, uv. 한 프로세스가 스케줄러 + REST + MCP를 `127.0.0.1:4000`에서 띄운다
  - `core/` — `scraper.py`(목록·상세 파싱, 이미지 저장, live/backfill), `db.py`(sqlite3 WAL, 스키마·마이그레이션), `tiles.py`(요약용 고정 크롭·JPEG 렌더), `crawl.py`(실행 게이트·상태), `scheduler.py`(APScheduler 15분), `queries.py`(REST·MCP 공용 조회)
  - `api/` — FastAPI REST(`/api/*`)와 `frontend/` 정적 서빙
  - `mcp/` — `server.py`에 tool 정의: 조회 `list_events`·`events_on`(일자별 JSON, 미요약 안내 포함)·`get_event`, 요약 `list_pending_summaries`·`get_summary_tiles`·`save_summary`. `schema.py`에 v2 pydantic과 에이전트용 안내문. `/mcp`에 Streamable HTTP로 노출하고 `stdio.py`는 같은 서버를 stdio로 띄우는 진입점(스케줄러 없이 같은 DB만 읽음)
- `.claude/agents/banner-summarizer.md` — 배너 1장을 요약하는 Sonnet 서브에이전트(도구는 `get_summary_tiles`·`save_summary`뿐). MCP 서버 이름을 `kis-event`로 등록해야 도구 이름이 맞는다
  - `main.py` — 앱 조립과 기동
- `frontend/index.html` — 빌드 없는 단일 파일 대시보드(이벤트 현황·대상 필터, 분석 완료/대기 수, 최근 스크랩 실행 이력, 신규 유입)
- `data/` — `events.db`, `images/`(원본 배너). 커밋하지 않는다. `KISEVENT_DATA_DIR`로 옮길 수 있다
- 로그 — `backend/core/logging.py`(loguru). 파일은 `%LOCALAPPDATA%\kisevent\logs\app.log`(macOS `~/Library/Application Support/kisevent/logs/`), 10MB 롤링 5개. 포맷 `시각 | 레벨 | ctx | 모듈:줄 | 메시지`, ctx는 live/backfill/scheduler/mcp/api/boot/tiles. 테이블은 `events`·`event_images`(status: pending|summarized|failed|superseded)·`image_summary`·`scrape_runs` 넷. uvicorn·apscheduler·httpx 표준 로깅은 여기로 합류하고 httpx 요청·access 로그는 DEBUG. 환경변수 `KISEVENT_LOG_DIR`, `KISEVENT_LOG_LEVEL`, `KISEVENT_FILE_LOG_LEVEL`, `KISEVENT_APP_DIR`
- `docs/event-page-research.md` — 사이트 실측 리서치와 설계 결정
- `SETUP.md` — 서빙 PC(Windows, 비개발자) 설치 절차. 에이전트가 그대로 수행한다
- `.mcp.json` — Claude Code가 이 폴더에서 `kis-event`(HTTP `/mcp`)를 자동 인식하게 하는 설정
- `run.bat` / `run-hidden.vbs` — Windows: 4000 포트 점유 프로세스를 죽이고 서버 기동(vbs는 창 없이, 작업 스케줄러용). `run.sh` — macOS/Linux 동일 동작

## 주요 명령 (레포 루트 기준)

- 환경: `uv sync`
- 서버: `./run.sh`(macOS) / `run.bat`(Windows) / `uv run python -m backend.main` — 모두 `127.0.0.1:4000`
- 즉시 스크랩 1회: `uv run python -m backend.core.scraper --mode live|backfill` (서버가 떠 있으면 대시보드 버튼이나 `POST /api/scrape?mode=`)
- 테스트: `uv run pytest`
- Claude Desktop 연결: `claude_desktop_config.json`에 `{"command": "uv", "args": ["--directory", "<레포 경로>", "run", "python", "-m", "backend.mcp.stdio"]}`. HTTP 커넥터를 받으면 `http://localhost:4000/mcp`도 된다
- Claude Code 연결: `claude mcp add --transport http kis-event http://localhost:4000/mcp`

## FronyBoard

This project is tracked by FronyBoard (project key: KIS).
Manage tasks through the FronyBoard MCP tools, following the FronyBoard server instructions.
Task tags: `frontend` / `backend` / `infra` / `docs` for where the work lands, plus
`design` or `test` for what kind it is. Reuse these rather than coining a synonym.
