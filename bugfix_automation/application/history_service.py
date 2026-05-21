from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bugfix_automation.config import Config
from bugfix_automation.storage.db import connect, ensure_schema
from bugfix_automation.storage.repositories import list_operation_events, read_ai_log_slice

PREVIEW_LIMIT = 80000


def list_operations(config: Config, limit: int = 100) -> dict[str, Any]:
    ensure_schema(config.storage_db_path)
    safe_limit = max(1, min(limit, 500))
    with connect(config.storage_db_path) as db:
        rows = db.execute(
            "SELECT * FROM operations ORDER BY started_at DESC LIMIT ?",
            (safe_limit,),
        ).fetchall()
        stats_rows = db.execute("SELECT kind, status, COUNT(*) AS count FROM operations GROUP BY kind, status").fetchall()
    items = [_normalize_operation(dict(row)) for row in rows]
    return {"items": items, "stats": _operation_stats([dict(row) for row in stats_rows])}


def operation_detail(config: Config, operation_id: str) -> dict[str, Any]:
    ensure_schema(config.storage_db_path)
    with connect(config.storage_db_path) as db:
        row = db.execute("SELECT * FROM operations WHERE id = ?", (operation_id,)).fetchone()
        if row is None:
            raise ValueError(f"操作记录不存在：{operation_id}")
        ai_rows = db.execute(
            "SELECT * FROM ai_sessions WHERE operation_id = ? ORDER BY started_at ASC",
            (operation_id,),
        ).fetchall()

    operation = _normalize_operation(dict(row))
    sessions = [_session_with_previews(dict(ai_row)) for ai_row in ai_rows]
    summary = operation.get("summary_data") or {}
    return {
        "operation": operation,
        "events": list_operation_events(config.storage_db_path, operation_id),
        "ai_sessions": sessions,
        "diff_preview": str(summary.get("diff_preview") or ""),
        "changed_files": summary.get("changed_files") if isinstance(summary.get("changed_files"), list) else [],
    }


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


def _normalize_operation(row: dict[str, Any]) -> dict[str, Any]:
    summary = str(row.get("summary") or "")
    row["summary_data"] = _parse_json_object(summary)
    row["summary_text"] = _summary_text(summary, row["summary_data"])
    return row


def _parse_json_object(text: str) -> dict[str, Any]:
    if not text.strip().startswith("{"):
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _summary_text(summary: str, summary_data: dict[str, Any]) -> str:
    if not summary_data:
        return summary
    for key in ("title", "message", "detail", "description"):
        value = summary_data.get(key)
        if isinstance(value, str) and value:
            return value
    return summary


def _session_with_previews(row: dict[str, Any]) -> dict[str, Any]:
    prompt_path = Path(row.get("prompt_path") or "")
    log_path = Path(row.get("log_path") or "")
    row["prompt_preview"] = _read_text_preview(prompt_path)
    row["log_preview"] = read_ai_log_slice(log_path, offset=0, limit=PREVIEW_LIMIT)["content"]
    row["summary_data"] = _parse_json_object(str(row.get("summary_json") or ""))
    return row


def _read_text_preview(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")[:PREVIEW_LIMIT]


def _operation_stats(rows: list[dict[str, Any]]) -> dict[str, int]:
    stats = {
        "total": 0,
        "runs": 0,
        "submitted": 0,
        "rejected": 0,
        "reworked": 0,
        "previewed": 0,
        "failed": 0,
    }
    for row in rows:
        kind = str(row.get("kind") or "")
        status = str(row.get("status") or "")
        count = int(row.get("count") or 0)
        stats["total"] += count
        if kind in {"run_one", "run_once"}:
            stats["runs"] += count
        if kind in {"fix-commit", "fix-approve"}:
            stats["submitted"] += count
        if kind == "fix-reject":
            stats["rejected"] += count
        if kind == "fix-rework":
            stats["reworked"] += count
        if kind in {"fix-preview", "fix-remove-preview"}:
            stats["previewed"] += count
        if status == "failed":
            stats["failed"] += count
    return stats
