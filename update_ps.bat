@echo off
chcp 65001 >nul
setlocal

rem repo: run from inside a clone, or use the install.bat default location
if exist "%~dp0pyproject.toml" (
    for %%i in ("%~dp0.") do set "REPO=%%~fi"
) else (
    set "REPO=%USERPROFILE%\project-kisevent"
)
if not exist "%REPO%\.git" echo 레포가 없습니다: %REPO% - install_ps.bat 또는 install_cmd.bat을 먼저 실행하세요. & goto :fail
cd /d "%REPO%"
where uv >nul 2>&1 || set "PATH=%USERPROFILE%\.local\bin;%PATH%"
echo === KIS Event update (%REPO%) ===
echo.

echo [1/3] 최신 코드 받기 (git fetch / pull)...
git fetch --prune || goto :fail
git pull --ff-only || goto :fail
git log --oneline -1

echo [2/3] 의존성 갱신 (uv sync)...
uv sync || goto :fail

echo [3/3] 서버 재시작...
schtasks /Query /TN "KISEvent" >nul 2>&1 && (
    schtasks /End /TN "KISEvent" >nul 2>&1
    schtasks /Run /TN "KISEvent" >nul || goto :fail
) || (
    wscript.exe "%REPO%\run-hidden.vbs"
)

set /a n=0
:wait
curl -s http://127.0.0.1:4000/api/health 2>nul | findstr /C:"\"ok\":true" >nul && goto :ok
set /a n+=1
if %n% geq 30 echo 서버가 60초 안에 뜨지 않았습니다. %LOCALAPPDATA%\kisevent\logs\app.log 를 확인하세요. & goto :fail
timeout /t 2 /nobreak >nul
goto :wait

:ok
echo.
echo === 업데이트 완료 === 서버가 새 코드로 다시 떴습니다. Claude Desktop은 재시작하면 새 도구 설명을 읽습니다.
pause
exit /b 0

:fail
echo.
echo === 업데이트 실패 === 위 오류를 확인하세요.
pause
exit /b 1
