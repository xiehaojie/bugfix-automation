from __future__ import annotations

from pathlib import Path
from typing import Any

from bugfix_automation.config import Config
from bugfix_automation.storage.db import connect, ensure_schema
from bugfix_automation.storage.repositories import list_operation_events, read_ai_log_slice


def list_operations(config: Config, limit: int = 100) -> dict[str, Any]:
    ensure_schema(config.storage_db_path)
    safe_limit = max(1, min(limit, 500))
    with connect(config.storage_db_path) as db:
        rows = db.execute(
            "SELECT * FROM operations ORDER BY started_at DESC LIMIT ?",
            (safe_limit,),
        ).fetchall()
    return {"items": [dict(row) for row in rows]}


def operation_events(config: Config, operation_id: str) -> dict[str, Any]:
    return {"items": list_operation_events(config.storage_db_path, operation_id)}


def list_excel_imports(config: Config, limit: int = 50) -> dict[str, Any]:
    ensure_schema(config.storage_db_path)
    safe_limit = max(1, min(limit, 200))
    with connect(config.storage_db_path) as db:
        rows = db.execute(
            "SELECT * FROM excel_import_batches ORDER BY created_at DESC LIMIT ?",
            (safe_limit,),
        ).fetchall()
    return {"items": [dict(row) for row in rows]}


def list_ai_sessions(config: Config, operation_id: str = "", limit: int = 50) -> dict[str, Any]:
    ensure_schema(config.storage_db_path)
    safe_limit = max(1, min(limit, 200))
    with connect(config.storage_db_path) as db:
        if operation_id:
            rows = db.execute(
                "SELECT * FROM ai_sessions WHERE operation_id = ? ORDER BY started_at DESC LIMIT ?",
                (operation_id, safe_limit),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM ai_sessions ORDER BY started_at DESC LIMIT ?",
                (safe_limit,),
            ).fetchall()
    return {"items": [dict(row) for row in rows]}


def ai_session_log(config: Config, ai_session_id: str, offset: int, limit: int) -> dict[str, Any]:
    ensure_schema(config.storage_db_path)
    with connect(config.storage_db_path) as db:
        row = db.execute("SELECT log_path FROM ai_sessions WHERE id = ?", (ai_session_id,)).fetchone()
    if row is None:
        raise ValueError(f"AI 会话不存在：{ai_session_id}")
    return read_ai_log_slice(Path(row["log_path"]), offset=offset, limit=limit)
