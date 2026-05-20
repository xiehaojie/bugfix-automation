from __future__ import annotations

from bugfix_automation.approval import approve_fix, count_pending, load_fix_items, reject_fix, remove_worktree, rework_fix
from bugfix_automation.config import Config


def list_items(config: Config):
    items = load_fix_items(config)
    return {"pending_count": count_pending(items), "items": items}


def approve(config: Config, branch: str) -> str:
    return approve_fix(config, branch)


def reject(config: Config, branch: str) -> None:
    reject_fix(config, branch)


def cleanup(config: Config, branch: str) -> None:
    remove_worktree(config, branch)


def rework(config: Config, branch: str, note: str = "", file_paths: list[str] | None = None, image_paths: list[str] | None = None) -> None:
    rework_fix(config, branch, note=note, file_paths=file_paths, image_paths=image_paths)
