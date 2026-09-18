# SETUP.md — 서빙 PC 설치 안내 (AI 에이전트용)

이 문서는 사용자가 "이 레포를 클론했어. MCP 서버 쓸 수 있게 셋팅해줘"라고 했을 때 AI 에이전트(Claude Code 또는 Claude Desktop)가 그대로 따라 하는 절차다. 사용자는 개발자가 아니므로 명령 실행·설정 파일 편집·검증을 전부 에이전트가 한다. 기본 환경은 Windows 10/11이며, macOS는 마지막 절에 차이만 적었다.

완료 기준: (1) 서버가 로그온 때마다 자동으로 떠서 `http://127.0.0.1:4000`에 대시보드가 열리고, (2) Claude Code와 Claude Desktop 양쪽에서 `kis-event` MCP 서버의 tool 7개가 보이며, (3) "지금 뱅키스 이벤트 뭐 있어?"에 답이 나온다.

## 0. 확인할 것
- 레포 경로를 절대경로로 잡는다. 아래에서 `<REPO>`는 예: `C:\Users\me\project-kisevent`.
- 이 PC에 `uv`가 있는지: `uv --version`. 없으면 1단계.
- Python은 따로 설치할 필요 없다. `uv`가 3.12를 받아온다.
- Node.js·Playwright·Docker는 필요 없다.

## 1. uv 설치 (없을 때만)
PowerShell:
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```
설치 위치는 `%USERPROFILE%\.local\bin\uv.exe`. 새 터미널을 열거나 `$env:Path += ";$env:USERPROFILE\.local\bin"`으로 PATH를 갱신한 뒤 `uv --version`으로 확인한다.

## 2. 의존성 설치
```powershell
cd <REPO>
uv sync
```
`.venv`가 만들어지고 `uv run pytest -q`가 통과하면 정상(네트워크 없이도 통과한다).

## 3. 서버 자동 실행 등록
서버 하나가 15분 주기 수집 + 대시보드 + MCP(HTTP)를 같이 띄운다. 로그온 시 창 없이 시작되도록 작업 스케줄러에 등록한다.
```powershell
schtasks /Create /F /SC ONLOGON /TN "KISEvent" /TR 'wscript.exe "<REPO>\run-hidden.vbs"'
schtasks /Run /TN "KISEvent"
```
30초 뒤 확인:
```powershell
curl http://127.0.0.1:4000/api/health
```
`{"ok":true,...}`가 나와야 한다. 첫 기동에 진행중 이벤트를 바로 수집한다. 지난 이벤트(최근 100건, 이미지 약 250MB)는 필요할 때만 대시보드의 "과거 100건 백필" 버튼으로 받는다 — 없어도 현재 이벤트 조회에는 지장이 없다.
- 수동으로 띄울 땐 `<REPO>\run.bat`(콘솔 창 있음). 4000 포트를 쓰던 프로세스는 스크립트가 먼저 종료한다.
- 로그: `%LOCALAPPDATA%\kisevent\logs\app.log` (10MB 롤링, 5개 보관). 문제가 생기면 여기부터 본다.
- 데이터: `<REPO>\data\events.db`, `<REPO>\data\images\`.

## 4. Claude Code 연결
레포에 `.mcp.json`이 있어서 `<REPO>`에서 Claude Code를 열면 `kis-event` 서버를 쓸지 묻는다 — 승인하면 끝. 다른 폴더에서도 쓰려면:
```powershell
claude mcp add --transport http --scope user kis-event http://127.0.0.1:4000/mcp
```
확인: Claude Code에서 `/mcp` → `kis-event` 연결됨, tool 7개.
서버 이름은 반드시 `kis-event`여야 한다. `.claude/agents/banner-summarizer.md`(배너 요약 서브에이전트)가 `mcp__kis-event__get_summary_tiles`·`mcp__kis-event__save_summary` 이름으로 도구를 찾기 때문이다.

## 5. Claude Desktop 연결
Claude Desktop은 localhost HTTP 커넥터를 받지 않을 수 있으므로 stdio로 등록한다. stdio 진입점은 서버 없이 같은 DB를 읽으므로 3단계 서버가 꺼져 있어도 조회는 된다(수집과 `sync_now`는 서버가 한다).
설정 파일 `%APPDATA%\Claude\claude_desktop_config.json`에 다음을 넣는다(파일이 없으면 만들고, 있으면 `mcpServers` 안에 항목만 추가). 경로의 `\`는 JSON이므로 `\\`로 쓴다.
```json
{
  "mcpServers": {
    "kis-event": {
      "command": "C:\\Users\\<USER>\\.local\\bin\\uv.exe",
      "args": ["--directory", "<REPO>", "run", "python", "-m", "backend.mcp.stdio"]
    }
  }
}
```
`command`는 `uv`가 아니라 `uv.exe` 절대경로를 쓴다(Desktop은 PATH를 못 볼 수 있다). 저장 후 Claude Desktop을 완전히 종료(트레이 아이콘까지)하고 다시 연다. 새 대화에서 도구 아이콘에 `kis-event`가 보이면 된다.
설정 > 커넥터에서 커스텀 커넥터로 `http://127.0.0.1:4000/mcp`가 등록되면 그것도 된다(둘 중 하나면 충분).

## 6. 최종 검증
1. 브라우저에서 `http://127.0.0.1:4000` — 진행중 이벤트 수가 0이 아니다.
2. Claude Code 또는 Desktop에서: "현재 뱅키스 고객대상 이벤트 뭐가 있어?" — 처음엔 미요약 배너를 먼저 요약(Claude Code는 `banner-summarizer` 서브에이전트를 이미지마다 병렬로 띄움)한 뒤 목록을 답한다. 진행중 30여 건 기준 몇 분 걸린다.
3. 대시보드의 "요약 완료" 수가 올라간다.

## 7. 문제가 생기면
| 증상 | 확인 |
|---|---|
| `uv` 명령을 못 찾음 | 새 터미널을 열거나 `%USERPROFILE%\.local\bin`을 PATH에 추가 |
| health가 응답 없음 | `schtasks /Query /TN KISEvent`로 작업 상태, `app.log` 마지막 줄. 4000 포트를 다른 프로그램이 쓰면 `run.bat`이 그 프로세스를 종료하므로 다른 포트가 필요하면 `run.bat`·`.mcp.json`·이 문서의 포트를 함께 바꾼다 |
| Claude Desktop에 서버가 안 보임 | JSON 문법(쉼표·`\\`), `uv.exe` 경로 존재, Desktop 완전 재시작. `Developer > Open MCP Log`에서 오류 확인 |
| 서브에이전트가 도구를 못 찾음 | MCP 서버 이름이 `kis-event`인지(`claude mcp list`) |
| 수집은 되는데 대상이 전부 "미상" | 정상. 대상은 배너 요약에서 나오므로 에이전트에게 요약을 시키면 채워진다 |
| 한글 로그가 깨짐 | 서버는 UTF-8로 강제하므로 콘솔 문제. `chcp 65001` 후 다시 본다 |

## macOS(개발 PC)에서의 차이
- uv 설치: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- 서버 수동 실행: `./run.sh`. 자동 실행이 필요하면 launchd에 같은 명령을 등록한다.
- Claude Desktop 설정 파일: `~/Library/Application Support/Claude/claude_desktop_config.json`, `command`는 `~/.local/bin/uv`.
- 로그: `~/Library/Application Support/kisevent/logs/app.log`
