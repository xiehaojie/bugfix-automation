from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bugfix_automation.config import Config
from bugfix_automation.storage.db import connect, ensure_schema
from bugfix_automation.storage.repositories import list_operation_events, read_ai_log_slice
from bugfix_automation.domain.task_state import load_task_states

PREVIEW_LIMIT = 80000
RUN_KINDS = {"run_one", "run_once"}


def list_operations(config: Config, limit: int = 100) -> dict[str, Any]:
    ensure_schema(config.storage_db_path)
    safe_limit = max(1, min(limit, 500))
    state_index = _task_state_index(config)
    with connect(config.storage_db_path) as db:
        rows = db.execute(
            "SELECT * FROM operations ORDER BY started_at ASC",
        ).fetchall()
    merged = _merge_related_operations([_normalize_operation(dict(row), state_index) for row in rows])
    return {"items": merged[:safe_limit], "stats": _operation_stats(merged)}


def operation_detail(config: Config, operation_id: str) -> dict[str, Any]:
    ensure_schema(config.storage_db_path)
    state_index = _task_state_index(config)
    with connect(config.storage_db_path) as db:
        row = db.execute("SELECT * FROM operations WHERE id = ?", (operation_id,)).fetchone()
        if row is None:
            raise ValueError(f"操作记录不存在：{operation_id}")
        selected = _normalize_operation(dict(row), state_index)
        all_rows = [_normalize_operation(dict(related), state_index) for related in db.execute("SELECT * FROM operations ORDER BY started_at ASC").fetchall()]
        related_rows = _find_related_group(all_rows, operation_id)
        operation_ids = [str(related["id"]) for related in related_rows]
        placeholders = ",".join("?" for _ in operation_ids) or "?"
        ai_rows = db.execute(
            f"SELECT * FROM ai_sessions WHERE operation_id IN ({placeholders}) ORDER BY started_at ASC",
            operation_ids or [operation_id],
        ).fetchall()
        event_rows = db.execute(
            f"SELECT * FROM operation_events WHERE operation_id IN ({placeholders}) ORDER BY created_at ASC",
            operation_ids or [operation_id],
        ).fetchall()

    operation = _merge_group(related_rows) if related_rows else selected
    sessions = [_session_with_previews(dict(ai_row)) for ai_row in ai_rows]
    summaries = [related.get("summary_data") or {} for related in related_rows]
    summary = _latest_summary_with(summaries, "diff_preview") or (operation.get("summary_data") or {})
    files_summary = _latest_summary_with(summaries, "changed_files") or summary
    diff_preview = str(summary.get("diff_preview") or "")
    changed_files = files_summary.get("changed_files") if isinstance(files_summary.get("changed_files"), list) else []
    if not diff_preview or not changed_files:
        commit_summary = _latest_summary_with(summaries, "commit_sha") or (operation.get("summary_data") or {})
        commit_diff_preview, commit_changed_files = _commit_artifacts(config, commit_summary)
        diff_preview = diff_preview or commit_diff_preview
        changed_files = changed_files or commit_changed_files
    return {
        "operation": operation,
        "events": [dict(event) for event in event_rows],
        "related_operations": related_rows,
        "ai_sessions": sessions,
        "diff_preview": diff_preview,
        "changed_files": changed_files,
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


def _normalize_operation(row: dict[str, Any], state_index: dict[str, dict[str, dict[str, Any]]] | None = None) -> dict[str, Any]:
    summary = str(row.get("summary") or "")
    row["started_at"] = _normalize_timestamp(str(row.get("started_at") or ""))
    if row.get("ended_at"):
        row["ended_at"] = _normalize_timestamp(str(row.get("ended_at") or ""))
    row["summary_data"] = _parse_json_object(summary)
    _apply_task_state(row, state_index or {})
    row["summary_text"] = _summary_text(summary, row["summary_data"])
    if not row.get("issue_id"):
        row["issue_id"] = _issue_id_from_branch(str(row.get("branch") or "")) or ""
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
    if summary_data.get("commit_sha"):
        return "已提交此修复"
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


def _merge_related_operations(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups = _group_related_operations(rows)
    merged = [_merge_group(group) for group in groups]
    return sorted(merged, key=lambda row: _sort_time(row.get("started_at")), reverse=True)


def _group_related_operations(rows: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    ordered_rows = sorted(rows, key=lambda row: _sort_time(row.get("started_at")))
    run_rows = [row for row in ordered_rows if row.get("kind") in RUN_KINDS]
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in ordered_rows:
        groups.setdefault(_operation_group_key(row, run_rows), []).append(row)
    return [sorted(group, key=lambda row: _sort_time(row.get("started_at"))) for group in groups.values()]


def _find_related_group(rows: list[dict[str, Any]], operation_id: str) -> list[dict[str, Any]]:
    for group in _group_related_operations(rows):
        if any(str(row.get("id") or "") == operation_id for row in group):
            return group
    return []


def _merge_group(group: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(group, key=lambda row: _sort_time(row.get("started_at")))
    run_ops = [row for row in ordered if row.get("kind") in RUN_KINDS]
    primary = dict(run_ops[-1] if run_ops else ordered[-1])
    actions = [row for row in ordered if row.get("kind") not in RUN_KINDS]
    if not actions:
        return primary

    action = actions[-1]
    primary_summary = primary.get("summary_data") or {}
    action_summary = action.get("summary_data") or {}
    merged_summary = {**primary_summary, **action_summary}
    if action.get("branch") and action.get("branch") != primary.get("branch"):
        merged_summary["action_branch"] = action.get("branch")
    primary.update(
        {
            "kind": action.get("kind"),
            "status": action.get("status"),
            "ended_at": action.get("ended_at") or action.get("started_at"),
            "summary": action.get("summary"),
            "summary_data": merged_summary,
            "summary_text": action.get("summary_text") or primary.get("summary_text"),
            "related_operation_ids": [row.get("id") for row in ordered],
        }
    )
    if not primary.get("issue_id"):
        primary["issue_id"] = action.get("issue_id") or _issue_id_from_branch(str(action.get("branch") or ""))
    if not primary.get("excel_row"):
        primary["excel_row"] = action.get("excel_row")
    return primary


def _operation_group_key(row: dict[str, Any], run_rows: list[dict[str, Any]]) -> str:
    linked_operation_id = str(row.get("linked_operation_id") or "")
    if linked_operation_id:
        return f"run:{linked_operation_id}"
    if row.get("kind") in RUN_KINDS:
        return f"run:{row.get('id', '')}"
    linked_run = _nearest_run_for_action(row, run_rows)
    if linked_run:
        return f"run:{linked_run.get('id', '')}"
    branch = str(row.get("branch") or "")
    return f"branch:{branch}" if branch else f"op:{row.get('id', '')}"


def _nearest_run_for_action(row: dict[str, Any], run_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    branch = str(row.get("branch") or "")
    original_branch = str(row.get("original_branch") or "")
    issue_id = str(row.get("issue_id") or "")
    excel_row = row.get("excel_row")
    action_time = _sort_time(row.get("started_at"))

    candidates = [
        run
        for run in run_rows
        if branch and branch in {str(run.get("branch") or ""), str(run.get("original_branch") or "")}
    ]
    if not candidates and issue_id:
        candidates = [
            run
            for run in run_rows
            if issue_id == str(run.get("issue_id") or "")
            and _same_excel_row(excel_row, run.get("excel_row"))
        ]
    if not candidates:
        return None

    before = [run for run in candidates if _sort_time(run.get("started_at")) <= action_time]
    pool = before or candidates
    return max(pool, key=lambda run: _sort_time(run.get("started_at")))


def _same_excel_row(left: Any, right: Any) -> bool:
    if not left or not right:
        return True
    try:
        return int(left) == int(right)
    except (TypeError, ValueError):
        return str(left) == str(right)


def _issue_id_from_branch(branch: str) -> str:
    match = re.match(r"^fix/(?:bug-)?(\d+)(?:-|$)", branch)
    return match.group(1) if match else ""


def _latest_summary_with(summaries: list[dict[str, Any]], key: str) -> dict[str, Any]:
    for summary in reversed(summaries):
        value = summary.get(key)
        if value:
            return summary
    return {}


def _commit_artifacts(config: Config, summary: dict[str, Any]) -> tuple[str, list[str]]:
    commit_sha = str(summary.get("commit_sha") or "")
    if not commit_sha:
        return "", []
    target_repo = config.target_repo
    if not target_repo.exists():
        return "", []
    try:
        diff = subprocess.run(
            ["git", "show", "--format=", "--find-renames", "--stat", "--patch", commit_sha, "--", config.target_app_path],
            cwd=target_repo,
            text=True,
            capture_output=True,
            check=True,
        ).stdout[:PREVIEW_LIMIT]
        files_output = subprocess.run(
            ["git", "show", "--format=", "--name-only", commit_sha, "--", config.target_app_path],
            cwd=target_repo,
            text=True,
            capture_output=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return "", []
    files = [line.strip() for line in files_output.splitlines() if line.strip()]
    return diff, files


def _task_state_index(config: Config) -> dict[str, dict[str, dict[str, Any]]]:
    by_branch: dict[str, dict[str, Any]] = {}
    by_operation: dict[str, dict[str, Any]] = {}
    for branch, state in load_task_states(config).items():
        if not isinstance(state, dict):
            continue
        normalized_state = {**state, "branch": str(state.get("branch") or branch)}
        state_branch = str(normalized_state.get("branch") or "")
        if state_branch:
            by_branch[state_branch] = normalized_state
        operation_id = str(normalized_state.get("operation_id") or "")
        if operation_id:
            by_operation[operation_id] = normalized_state
    return {"by_branch": by_branch, "by_operation": by_operation}


def _apply_task_state(row: dict[str, Any], state_index: dict[str, dict[str, dict[str, Any]]]) -> None:
    row_id = str(row.get("id") or "")
    branch = str(row.get("branch") or "")
    state = state_index.get("by_operation", {}).get(row_id)
    branch_state = state_index.get("by_branch", {}).get(branch)
    if branch_state and row.get("kind") not in RUN_KINDS:
        row["linked_operation_id"] = str(branch_state.get("operation_id") or "")
    state = state or branch_state
    if not state:
        return

    state_branch = str(state.get("branch") or "")
    if state_branch and row.get("kind") in RUN_KINDS and state_branch != branch:
        row["original_branch"] = branch
        row["branch"] = state_branch
    if not row.get("issue_id") and state.get("issue_id"):
        row["issue_id"] = str(state.get("issue_id") or "")
    if not row.get("excel_row") and state.get("excel_row"):
        row["excel_row"] = state.get("excel_row")
    if state.get("description"):
        row["description"] = state.get("description")


def _normalize_timestamp(value: str) -> str:
    if re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", value):
        parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        return parsed.astimezone().replace(tzinfo=None).isoformat(timespec="seconds")
    return value


def _sort_time(value: Any) -> datetime:
    if not value:
        return datetime.min
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return datetime.min


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
        stats["total"] += 1
        if kind in {"run_one", "run_once"}:
            stats["runs"] += 1
        if kind in {"fix-commit", "fix-approve"}:
            stats["submitted"] += 1
        if kind == "fix-reject":
            stats["rejected"] += 1
        if kind == "fix-rework":
            stats["reworked"] += 1
        if kind in {"fix-preview", "fix-remove-preview"}:
            stats["previewed"] += 1
        if status in {"failed", "conflict"}:
            stats["failed"] += 1
    return stats
