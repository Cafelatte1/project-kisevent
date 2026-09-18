@echo off
chcp 65001 >nul
setlocal
set "GIT_URL=https://github.com/Cafelatte1/project-kisevent"

rem 0. repo: run from inside a clone, or clone into %USERPROFILE%\project-kisevent
if exist "%~dp0pyproject.toml" (
    for %%i in ("%~dp0.") do set "REPO=%%~fi"
    goto :have_repo
)
set "REPO=%USERPROFILE%\project-kisevent"
where git >nul 2>&1 || (
    echo [0/4] git 설치 중 (winget)...
    winget install --id Git.Git -e --source winget --accept-source-agreements --accept-package-agreements || goto :fail
    set "PATH=%ProgramFiles%\Git\cmd;%PATH%"
)
if exist "%REPO%\.git" (
    echo [0/4] 레포 갱신: %REPO%
    git -C "%REPO%" pull --ff-only || goto :fail
) else (
    echo [0/4] 레포 클론: %REPO%
    git clone "%GIT_URL%" "%REPO%" || goto :fail
)
:have_repo
cd /d "%REPO%"
echo === KIS Event install (%REPO%) ===
echo.

rem 1. uv
set "UV="
for /f "delims=" %%i in ('where uv 2^>nul') do if not defined UV set "UV=%%i"
if not defined UV if exist "%USERPROFILE%\.local\bin\uv.exe" set "UV=%USERPROFILE%\.local\bin\uv.exe"
if not defined UV (
    echo [1/4] uv 설치 중...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex" || goto :fail
    set "UV=%USERPROFILE%\.local\bin\uv.exe"
)
if not exist "%UV%" echo uv를 찾을 수 없습니다: %UV% & goto :fail
echo [1/4] uv: %UV%
set "PATH=%USERPROFILE%\.local\bin;%PATH%"

rem 2. dependencies
echo [2/4] 의존성 설치 (uv sync)...
"%UV%" sync || goto :fail

rem 3. server on logon (Task Scheduler) + start now
echo [3/4] 서버 자동 실행 등록 (작업 스케줄러 KISEvent)...
schtasks /Create /F /SC ONLOGON /TN "KISEvent" /TR "wscript.exe \"%REPO%\run-hidden.vbs\"" >nul || goto :fail
schtasks /Run /TN "KISEvent" >nul || goto :fail

rem 4. Claude Desktop config (merge kis-event into mcpServers, keep the rest)
echo [4/4] Claude Desktop 커넥터 등록...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$p = Join-Path $env:APPDATA 'Claude\claude_desktop_config.json';" ^
  "New-Item -ItemType Directory -Force (Split-Path $p) | Out-Null;" ^
  "$cfg = [pscustomobject]@{};" ^
  "if (Test-Path $p) { Copy-Item $p ($p + '.bak') -Force; $raw = Get-Content $p -Raw; if ($raw.Trim()) { $cfg = $raw | ConvertFrom-Json } };" ^
  "if (-not $cfg.PSObject.Properties['mcpServers']) { $cfg | Add-Member -NotePropertyName mcpServers -NotePropertyValue ([pscustomobject]@{}) };" ^
  "$entry = [pscustomobject]@{ command = $env:UV; args = @('--directory', $env:REPO, 'run', 'python', '-m', 'backend.mcp.stdio') };" ^
  "if ($cfg.mcpServers.PSObject.Properties['kis-event']) { $cfg.mcpServers.'kis-event' = $entry } else { $cfg.mcpServers | Add-Member -NotePropertyName 'kis-event' -NotePropertyValue $entry };" ^
  "[IO.File]::WriteAllText($p, ($cfg | ConvertTo-Json -Depth 10), (New-Object Text.UTF8Encoding $false));" ^
  "Write-Host ('    ' + $p)" || goto :fail

rem health check
echo.
echo 서버 기동 확인 중...
set /a n=0
:wait
curl -s http://127.0.0.1:4000/api/health 2>nul | findstr /C:"\"ok\":true" >nul && goto :ok
set /a n+=1
if %n% geq 30 echo 서버가 60초 안에 뜨지 않았습니다. %LOCALAPPDATA%\kisevent\logs\app.log 를 확인하세요. & goto :fail
timeout /t 2 /nobreak >nul
goto :wait

:ok
echo.
echo === 설치 완료 ===
echo  - 대시보드: http://127.0.0.1:4000
echo  - Claude Desktop을 완전히 종료(트레이 아이콘까지)한 뒤 다시 열면 kis-event 커넥터가 보입니다.
echo  - 새 대화에서 "지금 뱅키스 이벤트 뭐 있어?" 로 확인하세요.
pause
exit /b 0

:fail
echo.
echo === 설치 실패 === 위 오류를 확인하세요.
pause
exit /b 1
