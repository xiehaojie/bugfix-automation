from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from bugfix_automation.storage.artifacts import file_size, sha256_file
from bugfix_automation.storage.db import connect, ensure_schema


def utc_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def stable_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def save_config_snapshot(db_path: Path, source: str, config: dict[str, Any]) -> str:
    ensure_schema(db_path)
    snapshot_json = stable_json(config)
    snapshot_id = new_id("cfg")
    with connect(db_path) as db:
        db.execute(
            "INSERT INTO config_snapshots(id, source, config_json, config_hash, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (snapshot_id, source, snapshot_json, sha256_text(snapshot_json), utc_now()),
        )
        db.commit()
    return snapshot_id


def create_operation(
    db_path: Path,
    *,
    kind: str,
    workspace_id: str,
    status: str,
    branch: str = "",
    issue_id: str = "",
    excel_row: int | None = None,
    config_snapshot_id: str | None = None,
    excel_import_batch_id: str | None = None,
    summary: str = "",
) -> str:
    ensure_schema(db_path)
    operation_id = new_id("op")
    with connect(db_path) as db:
        db.execute(
            "INSERT INTO operations("
            "id, kind, status, workspace_id, branch, issue_id, excel_row, started_at, "
            "config_snapshot_id, excel_import_batch_id, summary"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                operation_id,
                kind,
                status,
                workspace_id,
                branch,
                issue_id,
                excel_row,
                utc_now(),
                config_snapshot_id,
                excel_import_batch_id,
                summary,
            ),
        )
        db.commit()
    return operation_id


def finish_operation(db_path: Path, *, operation_id: str, status: str, summary: str = "") -> None:
    ensure_schema(db_path)
    with connect(db_path) as db:
        db.execute(
            "UPDATE operations SET status = ?, ended_at = ?, summary = ? WHERE id = ?",
            (status, utc_now(), summary, operation_id),
        )
        db.commit()


def update_operation_branch(db_path: Path, *, operation_id: str, branch: str) -> None:
    ensure_schema(db_path)
    with connect(db_path) as db:
        db.execute("UPDATE operations SET branch = ? WHERE id = ?", (branch, operation_id))
        db.commit()


def append_operation_event(
    db_path: Path,
    *,
    operation_id: str,
    event_type: str,
    status: str = "",
    message: str = "",
    payload: dict[str, Any] | None = None,
) -> str:
    ensure_schema(db_path)
    event_id = new_id("evt")
    payload_json = stable_json(payload or {})
    with connect(db_path) as db:
        db.execute(
            "INSERT INTO operation_events(id, operation_id, event_type, status, message, payload_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (event_id, operation_id, event_type, status, message, payload_json, utc_now()),
        )
        db.commit()
    return event_id


def list_operation_events(db_path: Path, operation_id: str) -> list[dict[str, Any]]:
    ensure_schema(db_path)
    with connect(db_path) as db:
        rows = db.execute(
            "SELECT * FROM operation_events WHERE operation_id = ? ORDER BY created_at ASC",
            (operation_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def save_excel_import(
    db_path: Path,
    *,
    original_filename: str,
    stored_path: Path,
    sheet_name: str,
    rows: list[dict[str, Any]],
    config_snapshot_id: str | None,
) -> str:
    ensure_schema(db_path)
    batch_id = new_id("xls")
    now = utc_now()
    with connect(db_path) as db:
        db.execute(
            "INSERT INTO excel_import_batches("
            "id, original_filename, stored_path, sha256, sheet_name, row_count, status, config_snapshot_id, created_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                batch_id,
                original_filename,
                str(stored_path),
                sha256_file(stored_path),
                sheet_name,
                len(rows),
                "imported",
                config_snapshot_id,
                now,
            ),
        )
        for row in rows:
            row_json = stable_json(row)
            excel_row = int(row.get("_excel_row") or 0)
            issue_id = str(row.get("序号") or "")
            description = str(row.get("问题描述") or "")
            db.execute(
                "INSERT INTO excel_import_rows("
                "id, batch_id, excel_row, issue_id, row_json, description, assignee, "
                "requester_status, assignee_status, row_hash, created_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    new_id("row"),
                    batch_id,
                    excel_row,
                    issue_id,
                    row_json,
                    description,
                    str(row.get("对接人") or ""),
                    str(row.get("提出人状态") or ""),
                    str(row.get("对接人状态") or ""),
                    sha256_text(row_json),
                    now,
                ),
            )
        db.commit()
    return batch_id


def create_ai_session(
    db_path: Path,
    *,
    operation_id: str,
    provider: str,
    cli_tool: str,
    workspace_path: Path,
    prompt_path: Path,
    log_path: Path,
    ai_session_id: str | None = None,
) -> str:
    ensure_schema(db_path)
    session_id = ai_session_id or new_id("ai")
    with connect(db_path) as db:
        db.execute(
            "INSERT INTO ai_sessions("
            "id, operation_id, provider, cli_tool, workspace_path, prompt_path, log_path, status, started_at, prompt_sha256"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                operation_id,
                provider,
                cli_tool,
                str(workspace_path),
                str(prompt_path),
                str(log_path),
                "running",
                utc_now(),
                sha256_file(prompt_path) if prompt_path.exists() else "",
            ),
        )
        db.commit()
    return session_id


def finish_ai_session(
    db_path: Path,
    *,
    ai_session_id: str,
    status: str,
    log_path: Path,
    summary: dict[str, Any],
) -> None:
    ensure_schema(db_path)
    with connect(db_path) as db:
        db.execute(
            "UPDATE ai_sessions SET status = ?, ended_at = ?, log_sha256 = ?, log_size_bytes = ?, summary_json = ? WHERE id = ?",
            (
                status,
                utc_now(),
                sha256_file(log_path) if log_path.exists() else "",
                file_size(log_path),
                stable_json(summary),
                ai_session_id,
            ),
        )
        db.commit()


def index_ai_log_segments(
    db_path: Path,
    *,
    ai_session_id: str,
    log_path: Path,
    segment_size: int = 65536,
) -> None:
    ensure_schema(db_path)
    data = log_path.read_bytes() if log_path.exists() else b""
    now = utc_now()
    with connect(db_path) as db:
        db.execute("DELETE FROM ai_log_segments WHERE ai_session_id = ?", (ai_session_id,))
        line_start = 1
        for seq, offset_start in enumerate(range(0, len(data), segment_size), start=1):
            chunk = data[offset_start : offset_start + segment_size]
            offset_end = offset_start + len(chunk)
            text = chunk.decode("utf-8", errors="replace")
            newline_count = text.count("\n")
            line_end = line_start + newline_count
            db.execute(
                "INSERT INTO ai_log_segments("
                "id, ai_session_id, seq, offset_start, offset_end, line_start, line_end, preview, created_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    new_id("seg"),
                    ai_session_id,
                    seq,
                    offset_start,
                    offset_end,
                    line_start,
                    line_end,
                    text[:240],
                    now,
                ),
            )
            line_start = line_end + 1
        db.commit()


def read_ai_log_slice(log_path: Path, *, offset: int, limit: int) -> dict[str, Any]:
    safe_offset = max(0, offset)
    safe_limit = max(1, min(limit, 200000))
    if not log_path.exists():
        return {"offset": safe_offset, "next_offset": safe_offset, "content": "", "size": 0}
    size = log_path.stat().st_size
    with log_path.open("rb") as file:
        file.seek(min(safe_offset, size))
        data = file.read(safe_limit)
    return {
        "offset": safe_offset,
        "next_offset": min(safe_offset + len(data), size),
        "content": data.decode("utf-8", errors="replace"),
        "size": size,
    }
