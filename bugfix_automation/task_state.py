from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import threading
from typing import Any

from bugfix_automation.config import Config
from bugfix_automation.filtering import BugRecord
from bugfix_automation.storage.repositories import append_operation_event, update_operation_branch


ACTIVE_STATUSES = {"queued", "running", "verifying", "reworking"}
_LOCK = threading.Lock()


def task_state_path(config: Config) -> Path:
    return config.runs_root / "task-state.json"


def load_task_states(config: Config) -> dict[str, dict[str, Any]]:
    path = task_state_path(config)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    states = payload.get("tasks", {})
    return states if isinstance(states, dict) else {}


def task_state(config: Config, branch: str) -> dict[str, Any]:
    state = load_task_states(config).get(branch, {})
    return state if isinstance(state, dict) else {}


def is_task_active(config: Config, branch: str) -> bool:
    state = task_state(config, branch)
    status = str(state.get("status", ""))
    if status not in ACTIVE_STATUSES:
        return False
    pid = int(state.get("pid") or 0)
    return pid <= 0 or _pid_exists(pid)


def set_task_state(
    config: Config,
    branch: str,
    status: str,
    bug: BugRecord | None = None,
    detail: str = "",
    phase: str = "",
    pid: int | None = None,
    image_paths: list[Path] | None = None,
    operation_id: str | None = None,
) -> dict[str, Any]:
    now = datetime.now().isoformat(timespec="seconds")
    with _LOCK:
        states = load_task_states(config)
        previous = states.get(branch, {}) if isinstance(states.get(branch), dict) else {}
        next_state: dict[str, Any] = {
            **previous,
            "branch": branch,
            "status": status,
            "phase": phase,
            "detail": detail,
            "pid": os.getpid() if pid is None else pid,
            "updated_at": now,
        }
        if bug is not None:
            next_state.update(
                {
                    "issue_id": bug.issue_id,
                    "excel_row": bug.excel_row,
                    "description": bug.description,
                }
            )
        if status in ACTIVE_STATUSES and not next_state.get("started_at"):
            next_state["started_at"] = now
        if status not in ACTIVE_STATUSES:
            next_state["ended_at"] = now
        if image_paths is not None:
            next_state["images"] = [str(path) for path in image_paths]
        if operation_id is not None:
            next_state["operation_id"] = operation_id
        states[branch] = next_state
        _write_states(task_state_path(config), states)
        stored_operation_id = str(next_state.get("operation_id") or "")
        if stored_operation_id:
            append_operation_event(
                config.storage_db_path,
                operation_id=stored_operation_id,
                event_type="task_state",
                status=status,
                message=detail,
                payload={"branch": branch, "phase": phase, "pid": next_state.get("pid")},
            )
        return next_state


def rename_task_state(config: Config, old_branch: str, new_branch: str) -> None:
    with _LOCK:
        states = load_task_states(config)
        state = states.pop(old_branch, {}) if isinstance(states.get(old_branch), dict) else {}
        if state:
            state["branch"] = new_branch
            states[new_branch] = state
            _write_states(task_state_path(config), states)
            operation_id = str(state.get("operation_id") or "")
            if operation_id:
                update_operation_branch(config.storage_db_path, operation_id=operation_id, branch=new_branch)


def _write_states(path: Path, states: dict[str, dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f"{path.suffix}.tmp")
    tmp.write_text(json.dumps({"tasks": states}, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True
