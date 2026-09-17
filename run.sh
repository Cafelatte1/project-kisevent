#!/bin/sh
cd "$(dirname "$0")"
pids=$(lsof -ti tcp:4000 2>/dev/null)
[ -n "$pids" ] && kill $pids 2>/dev/null
exec uv run uvicorn backend.main:app --host 127.0.0.1 --port 4000
