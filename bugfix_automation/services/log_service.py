from __future__ import annotations

import asyncio
import json
from typing import Any

from bugfix_automation.config import Config
from bugfix_automation.orchestration.bug_runner import codex_log_path
from bugfix_automation.storage.repositories import read_ai_log_slice


def log_payload(config: Config, branch: str, offset: int | None = None, limit: int = 120000) -> dict[str, Any]:
    if not branch:
        return {"branch": "", "path": "", "content": ""}
    path = codex_log_path(config, branch)
    if not path.exists():
        return {"branch": branch, "path": str(path), "content": ""}
    size = path.stat().st_size
    start = max(0, size - limit) if offset is None else max(0, offset)
    payload = read_ai_log_slice(path, offset=start, limit=limit)
    return {"branch": branch, "path": str(path), **payload}


def sse_data(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n"


async def log_event_stream(
    config: Config,
    branch: str,
    *,
    limit: int = 120000,
    poll_interval: float = 0.5,
    follow: bool = True,
):
    if not branch:
        yield sse_data({"type": "snapshot", "branch": "", "path": "", "content": ""})
        return

    initial = log_payload(config, branch, limit=limit)
    yield sse_data({"type": "snapshot", **initial})
    offset = int(initial.get("next_offset") or initial.get("size") or 0)
    path = codex_log_path(config, branch)
    keepalive_ticks = 0

    while follow:
        await asyncio.sleep(poll_interval)
        keepalive_ticks += 1

        if not path.exists():
            if offset:
                offset = 0
                yield sse_data({"type": "snapshot", "branch": branch, "path": str(path), "content": "", "reset": True})
            continue

        size = path.stat().st_size
        if size < offset:
            payload = read_ai_log_slice(path, offset=0, limit=limit)
            offset = int(payload.get("next_offset") or 0)
            yield sse_data({"type": "snapshot", "branch": branch, "path": str(path), "reset": True, **payload})
            continue

        if size > offset:
            payload = read_ai_log_slice(path, offset=offset, limit=limit)
            offset = int(payload.get("next_offset") or offset)
            yield sse_data({"type": "append", "branch": branch, "path": str(path), **payload})
            keepalive_ticks = 0
            continue

        if keepalive_ticks >= max(1, int(15 / poll_interval)):
            yield ": keep-alive\n\n"
            keepalive_ticks = 0
