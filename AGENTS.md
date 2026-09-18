# AGENTS.md — Codex(GPT)용 안내

이 문서는 Codex CLI / ChatGPT Codex 앱이 읽는다. Claude Code용 안내는 `CLAUDE.md`이며 프로젝트 설명·디렉토리·명령·FronyBoard 규칙은 그 파일이 원본이다. 개발 작업을 할 때는 `CLAUDE.md`를 먼저 읽는다.

## 사용자가 "셋팅해줘"라고 하면
`SETUP.md`를 처음부터 끝까지 그대로 수행한다. Codex 연결은 그 문서의 "Codex(GPT) 연결" 절을 따른다.

## 이벤트 질문에 답하는 흐름 (kis-event MCP)
한국투자증권 이벤트는 배너 이미지 안에 내용이 있어, 질문에 답하기 전에 관련 배너가 요약돼 있어야 한다.
1. 대화에서 이벤트를 처음 조회하기 전에 `sync_now`를 한 번 부른다(완료까지 기다렸다 돌아온다). 같은 대화에서 다시 부를 필요는 없다.
2. `list_events(target)` 또는 `events_on(date, target)`로 대상 이벤트를 고른다. 응답의 `pending_summaries`가 0보다 크면 미요약 배너가 있다.
3. 미요약 image_id는 `sync_now` 응답의 `batches`(진행중 이벤트)나 `list_pending_summaries(event_nums=…)`의 `batches`로 받는다. 이미 2개씩 묶여 있다.
4. **묶음마다 커스텀 에이전트 `event-analyzer`를 하나씩, 전부 동시에 띄운다**(예: 5개 → [[a,b],[c,d],[e]] 3개). 메인 세션이 `get_summary_tiles`를 직접 부르며 순차 처리하는 것은 금지다. 에이전트는 `~/.codex/agents/event-analyzer.toml`에 있어야 하며, 없으면 이 레포의 `.codex/agents/event-analyzer.toml`을 그 위치로 복사한다. 에이전트를 정말 띄울 수 없을 때만 `get_summary_tiles(image_id)` → `save_summary(image_id, summary)`를 image_id별로 직접 한다.
5. 다시 조회해 답한다. 요약 전 이벤트는 `target_types`가 null이라 대상 필터가 확정되지 않았으므로 결과에 남는다.

지난 이벤트 백필은 대시보드(`http://127.0.0.1:4000`)의 버튼으로만 한다. MCP에는 없다.

## 요약 JSON(schema_version 2)
`get_summary_tiles` 응답의 안내문이 원본이다. 순서는 `analysis(이미지 서술) → block_found → target{types,text,conditions,exclusions} → criteria{text,products,performance}|null`. `block_found`가 false면 target·criteria는 쓰지 않는다. `save_summary`가 `ok:false`를 주면 `errors`대로 고쳐 다시 저장한다.
