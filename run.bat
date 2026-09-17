@echo off
chcp 65001 >nul
cd /d %~dp0
for /f "tokens=5" %%p in ('netstat -ano ^| findstr :4000 ^| findstr LISTENING') do taskkill /PID %%p /F >nul 2>&1
uv run uvicorn backend.main:app --host 127.0.0.1 --port 4000
