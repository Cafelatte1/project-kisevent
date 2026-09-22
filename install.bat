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
where git >nul 2>&1 || call :install_git || goto :fail
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
schtasks /Create /F /SC ONLOGON /TN "KISEvent" /TR "wscript.exe \"%REPO%\run-hidden.vbs\"" >nul || (
    echo 작업 스케줄러 등록 실패. install.bat을 마우스 오른쪽 - "관리자 권한으로 실행"으로 다시 실행해 보세요.
    goto :fail
)
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

rem --- git: try winget, otherwise download the official Git for Windows installer and run it silently ---
:install_git
if exist "%ProgramFiles%\Git\cmd\git.exe" goto :git_ok
echo [0/4] git 설치 중 - winget...
where winget >nul 2>&1 && winget install --id Git.Git -e --source winget --accept-source-agreements --accept-package-agreements
if exist "%ProgramFiles%\Git\cmd\git.exe" goto :git_ok
echo [0/4] winget 실패 - git-scm.com 설치 파일을 직접 받아 설치합니다 (UAC 창이 뜨면 '예')...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$a = (irm https://api.github.com/repos/git-for-windows/git/releases/latest).assets | ? { $_.name -match '^Git-.*-64-bit\.exe$' } | select -First 1;" ^
  "$f = Join-Path $env:TEMP $a.name; iwr $a.browser_download_url -OutFile $f;" ^
  "Start-Process $f -ArgumentList '/VERYSILENT','/NORESTART' -Wait" || exit /b 1
if not exist "%ProgramFiles%\Git\cmd\git.exe" echo git 설치 실패. https://git-scm.com/download/win 에서 직접 설치 후 다시 실행하세요. & exit /b 1
:git_ok
set "PATH=%ProgramFiles%\Git\cmd;%PATH%"
exit /b 0
