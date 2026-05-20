from __future__ import annotations

from typing import Any

from bugfix_automation.config import Config
from bugfix_automation.runner import codex_log_path


def log_payload(config: Config, branch: str) -> dict[str, Any]:
    if not branch:
        return {"branch": "", "path": "", "content": ""}
    path = codex_log_path(config, branch)
    if not path.exists():
        return {"branch": branch, "path": str(path), "content": ""}
    content = path.read_text(encoding="utf-8", errors="replace")
    return {"branch": branch, "path": str(path), "content": content[-120000:]}
