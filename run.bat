@echo off
for /f "tokens=5" %%p in ('netstat -ano ^| findstr :4000 ^| findstr LISTENING') do taskkill /PID %%p /F
uv run uvicorn backend.main:app --port 4000
