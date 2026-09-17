# CLAUDE.md

## 프로젝트

KIS Event: 한국투자증권 이벤트 공고(영업점·뱅키스 고객대상)를 15분 주기로 스크랩해 SQLite에 쌓고, Claude Desktop이 MCP로 붙어 "지금 영업점 고객대상 이벤트가 뭐가 있어?"에 답하는 로컬 개인용 서비스.
이벤트 내용은 거의 전부 세로 7k~30k px 배너 이미지 안에 있다. 백엔드는 이미지를 여백 행에서 타일로 잘라 MCP로 넘기고, 에이전트가 타일을 전사(`image_tiles.text`)한 뒤 스키마 v1 JSON으로 구조화(`image_analysis`)해 저장한다. 에이전트는 미분석 이미지가 있으면 답하기 전에 분석을 먼저 마친다. 사이트 구조·템플릿 분류·타일 전략·메타데이터 스키마의 근거는 `docs/event-page-research.md`를 따른다.
스크랩은 로그인·JS 실행 없는 GET + HTML 파싱이며, 목록은 `currentPage`를 빈 페이지까지 순회하고 `#ifrmContent`가 없는 구형 템플릿은 `<!--b:s-->…<!--b:e-->` 구간으로 폴백한다. 이미지는 URL 또는 sha256이 바뀔 때만 다시 받고 다시 분석한다.

## 디렉토리 구조

- `backend/` — Python 3.12, uv. 한 프로세스가 스케줄러 + REST + MCP를 `127.0.0.1:4000`에서 띄운다
  - `core/` — `scraper.py`(목록·상세 파싱, 이미지 저장), `db.py`(sqlite3 WAL, 스키마), `tiles.py`(여백 행 절단), `scheduler.py`(APScheduler 15분)
  - `api/` — FastAPI REST(`/api/*`)와 `frontend/` 정적 서빙
  - `mcp/` — FastMCP tool 정의, `/mcp`에 Streamable HTTP로 마운트. `list_events`·`get_pending_tiles`·`save_tile_text`·`get_transcript`·`save_analysis`·`get_event`
  - `main.py` — 앱 조립과 기동
- `frontend/index.html` — 빌드 없는 단일 파일 대시보드(이벤트 현황·대상 필터, 분석 완료/대기 수, 최근 스크랩 실행 이력, 신규 유입)
- `data/` — `events.db`, `images/`(원본 배너). 커밋하지 않는다
- `docs/event-page-research.md` — 사이트 실측 리서치와 설계 결정
- `run.bat` — Windows에서 4000 포트 점유 프로세스를 죽이고 서버 기동

## 주요 명령 (레포 루트 기준)

- 환경: `uv sync`
- 서버: `uv run uvicorn backend.main:app --port 4000` (Windows는 `run.bat`)
- 즉시 스크랩 1회: `uv run python -m backend.core.scraper`
- 테스트: `uv run pytest`
- Claude Desktop 연결: 커넥터에 `http://localhost:4000/mcp` 등록, 안 되면 `npx mcp-remote http://localhost:4000/mcp`를 stdio로 등록

## FronyBoard

This project is tracked by FronyBoard (project key: KIS).
Manage tasks through the FronyBoard MCP tools, following the FronyBoard server instructions.
Task tags: `frontend` / `backend` / `infra` / `docs` for where the work lands, plus
`design` or `test` for what kind it is. Reuse these rather than coining a synonym.
