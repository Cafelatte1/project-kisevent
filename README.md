# KIS Event

한국투자증권 이벤트 공고를 수집해 SQLite에 쌓고, AI 에이전트가 MCP로 붙어 "지금 영업점 고객대상 이벤트 뭐 있어?"에 답하는 로컬 개인용 서비스. 이벤트 내용은 배너 이미지 안에 있어 에이전트가 이미지를 읽어 대상·기준을 요약한 뒤 답한다.

- 설치·연결: `SETUP.md` (에이전트에게 "셋팅해줘"라고 하면 그대로 수행)
- 대시보드(상태판): http://127.0.0.1:4000
- MCP: HTTP `http://127.0.0.1:4000/mcp` (Claude Code는 `.mcp.json` 자동 인식), Claude Desktop은 stdio
- 개발 안내: `CLAUDE.md`, 설계 근거: `docs/event-page-research.md`

## 에이전트 모델 요구 사양

역할이 둘이다.
- **메인 세션** — 사용자 질문을 받아 `sync_now → 조회 → (미요약이면 분석 지시) → 답변` 흐름을 지휘한다.
- **서브에이전트 `event-analyzer`** — 배너 1장을 읽어 대상·기준 JSON을 만들고 저장한다. Claude Code에서는 `.claude/agents/event-analyzer.md`가 미요약 이미지마다 하나씩 병렬로 뜬다. 서브에이전트가 없는 환경(Claude Desktop)에서는 메인 세션이 같은 일을 직접 한다.

| | 서브에이전트 (`event-analyzer`) | 메인 세션 |
|---|---|---|
| **Claude** 최소 / 권장 | Sonnet low / Sonnet medium | Sonnet medium / Sonnet high |
| **GPT** 최소 / 권장 | GPT Luna medium / GPT Luna high | GPT Luna high / GPT Luna xhigh |

기본 설정은 서브에이전트 Sonnet medium(`effort: medium`)이며, 진행중 33건 + 종료 20건 검증에서 정보 블록 인식 53/53, 대상 판정 오류 0이었다(`docs/event-page-research.md` §8).
