@echo off
chcp 65001 >nul
setlocal
set "ZIP_URL=https://github.com/Cafelatte1/project-kisevent/archive/refs/heads/main.zip"

rem repo: run from inside a clone, or the install.bat default location
if exist "%~dp0pyproject.toml" (
    for %%i in ("%~dp0.") do set "REPO=%%~fi"
) else (
    set "REPO=%USERPROFILE%\project-kisevent"
)
if not exist "%REPO%\pyproject.toml" echo 레포가 없습니다: %REPO% - install.bat을 먼저 실행하세요. & goto :fail
cd /d "%REPO%"
echo === KIS Event update - %REPO% ===
echo.

echo [1/3] 최신 코드 받기...
if exist "%REPO%\.git" (
    git fetch --prune || goto :fail
    git pull --ff-only || goto :fail
    git log --oneline -1
) else (
    call :fetch_zip || goto :fail
)

set "UV="
for /f "delims=" %%i in ('where uv 2^>nul') do if not defined UV set "UV=%%i"
if not defined UV if exist "%USERPROFILE%\.local\bin\uv.exe" set "UV=%USERPROFILE%\.local\bin\uv.exe"
if not defined UV echo uv를 찾을 수 없습니다. install.bat을 먼저 실행하세요. & goto :fail

echo [2/3] 의존성 갱신 - uv sync...
"%UV%" sync || goto :fail

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

rem --- no git: download the source zip and overwrite the code, data stays ---
:fetch_zip
set "TMPZ=%TEMP%\kisevent-src.zip"
set "TMPD=%TEMP%\project-kisevent-main"
curl -L -f -s -o "%TMPZ%" "%ZIP_URL%" || exit /b 1
if exist "%TMPD%" rmdir /s /q "%TMPD%"
tar -xf "%TMPZ%" -C "%TEMP%" || exit /b 1
xcopy /e /h /i /y /q "%TMPD%\*" "%REPO%\" >nul || exit /b 1
rmdir /s /q "%TMPD%"
del /q "%TMPZ%"
exit /b 0
