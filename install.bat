@echo off
chcp 65001 >nul
setlocal
set "GIT_URL=https://github.com/Cafelatte1/project-kisevent"
set "ZIP_URL=https://github.com/Cafelatte1/project-kisevent/archive/refs/heads/main.zip"
set "UV_URL=https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip"

where curl >nul 2>&1 || (echo curl.exe가 없습니다. Windows 10 1803 이상이 필요합니다. & goto :fail)
where tar >nul 2>&1 || (echo tar.exe가 없습니다. Windows 10 1803 이상이 필요합니다. & goto :fail)

rem 0. repo: run from inside a clone, else clone with git, else download the source zip
if exist "%~dp0pyproject.toml" (
    for %%i in ("%~dp0.") do set "REPO=%%~fi"
    goto :have_repo
)
set "REPO=%USERPROFILE%\project-kisevent"
where git >nul 2>&1 && goto :use_git
echo [0/4] git이 없어 소스 zip으로 받습니다: %REPO%
call :fetch_zip || goto :fail
goto :have_repo
:use_git
if exist "%REPO%\.git" (
    echo [0/4] 레포 갱신: %REPO%
    git -C "%REPO%" pull --ff-only || goto :fail
) else (
    echo [0/4] 레포 클론: %REPO%
    git clone "%GIT_URL%" "%REPO%" || goto :fail
)
:have_repo
cd /d "%REPO%"
echo === KIS Event install - %REPO% ===
echo.

rem 1. uv - a single exe, no installer
set "UV="
for /f "delims=" %%i in ('where uv 2^>nul') do if not defined UV set "UV=%%i"
if not defined UV if exist "%USERPROFILE%\.local\bin\uv.exe" set "UV=%USERPROFILE%\.local\bin\uv.exe"
if not defined UV (
    echo [1/4] uv 내려받는 중...
    if not exist "%USERPROFILE%\.local\bin" mkdir "%USERPROFILE%\.local\bin"
    curl -L -f -s -o "%TEMP%\uv.zip" "%UV_URL%" || goto :fail
    tar -xf "%TEMP%\uv.zip" -C "%USERPROFILE%\.local\bin" || goto :fail
    del /q "%TEMP%\uv.zip"
    set "UV=%USERPROFILE%\.local\bin\uv.exe"
)
if not exist "%UV%" echo uv를 찾을 수 없습니다: %UV% & goto :fail
echo [1/4] uv: %UV%

rem 2. dependencies
echo [2/4] 의존성 설치 - uv sync...
"%UV%" sync || goto :fail

rem 3. server on logon (Task Scheduler) + start now
echo [3/4] 서버 자동 실행 등록 - 작업 스케줄러 KISEvent...
schtasks /Create /F /SC ONLOGON /TN "KISEvent" /TR "wscript.exe \"%REPO%\run-hidden.vbs\"" >nul || (
    echo 작업 스케줄러 등록 실패. install.bat을 마우스 오른쪽 - 관리자 권한으로 실행으로 다시 해 보세요.
    goto :fail
)
schtasks /Run /TN "KISEvent" >nul || goto :fail

rem 4. Claude Desktop config - merge kis-event into mcpServers, keep the rest
echo [4/4] Claude Desktop 커넥터 등록...
"%UV%" run python scripts\register_desktop.py "%UV%" "%REPO%" || goto :fail

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
echo  - Claude Desktop을 완전히 종료한 뒤 - 트레이 아이콘까지 - 다시 열면 kis-event 커넥터가 보입니다.
echo  - 새 대화에서 "지금 뱅키스 이벤트 뭐 있어?" 로 확인하세요.
pause
exit /b 0

:fail
echo.
echo === 설치 실패 === 위 오류를 확인하세요.
pause
exit /b 1

rem --- download the source zip and unpack it into %REPO% (no git needed) ---
:fetch_zip
set "TMPZ=%TEMP%\kisevent-src.zip"
set "TMPD=%TEMP%\project-kisevent-main"
curl -L -f -s -o "%TMPZ%" "%ZIP_URL%" || exit /b 1
if exist "%TMPD%" rmdir /s /q "%TMPD%"
tar -xf "%TMPZ%" -C "%TEMP%" || exit /b 1
if not exist "%REPO%" mkdir "%REPO%"
xcopy /e /h /i /y /q "%TMPD%\*" "%REPO%\" >nul || exit /b 1
rmdir /s /q "%TMPD%"
del /q "%TMPZ%"
exit /b 0
