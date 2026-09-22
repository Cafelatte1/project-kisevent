"""Add the kis-event stdio server to claude_desktop_config.json, keeping other entries."""

import json
import os
import shutil
import sys
from pathlib import Path

uv, repo = sys.argv[1], sys.argv[2]
path = Path(os.environ["APPDATA"]) / "Claude" / "claude_desktop_config.json"
path.parent.mkdir(parents=True, exist_ok=True)

config = {}
if path.exists():
    shutil.copyfile(path, path.with_name(path.name + ".bak"))
    text = path.read_text(encoding="utf-8-sig").strip()
    if text:
        config = json.loads(text)

config.setdefault("mcpServers", {})["kis-event"] = {
    "command": uv,
    "args": ["--directory", repo, "run", "python", "-m", "backend.mcp.stdio"],
}
path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"    {path}")
