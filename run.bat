@echo off
setlocal

set PORT=4000

echo [1/2] %PORT% 포트 사용 중인 프로세스 확인...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":%PORT%" ^| findstr "LISTENING"') do (
	echo   PID %%p 종료
	taskkill /PID %%p /F >nul 2>&1
)

echo [2/2] 서버 시작...
node server.js

endlocal
