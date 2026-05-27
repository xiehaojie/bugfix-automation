from __future__ import annotations

import re
from pathlib import Path


def ai_cli_kind(cli_tool: str) -> str:
    name = Path(cli_tool).name.lower()
    stem = Path(cli_tool).stem.lower()
    if "claude" in name or "claude" in stem:
        return "claude"
    if "codex" in name or "codex" in stem:
        return "codex"
    return "codex"


def ai_cli_label(cli_tool: str) -> str:
    kind = ai_cli_kind(cli_tool)
    if kind == "claude":
        return "Claude Code"
    if kind == "codex":
        return "Codex"
    return "AI CLI"


def ai_log_dir_name(cli_tool: str) -> str:
    kind = ai_cli_kind(cli_tool)
    if kind in {"claude", "codex"}:
        return kind
    stem = Path(cli_tool).stem or "ai"
    return re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-") or "ai"


def ai_cli_command(cli_tool: str, worktree_path: str, prompt: str, image_paths: list[Path] | None = None) -> list[str]:
    if ai_cli_kind(cli_tool) == "claude":
        command = [
            cli_tool,
            "--print",
            "--permission-mode",
            "bypassPermissions",
        ]
        image_dirs = _unique_existing_parent_dirs(image_paths or [])
        if image_dirs:
            command.append("--add-dir")
            command.extend(str(path) for path in image_dirs)
        return command

    command = [
        cli_tool,
        "exec",
        "--full-auto",
        "--cd",
        worktree_path,
    ]
    for image_path in image_paths or []:
        command.extend(["--image", str(image_path)])
    command.append("-")
    return command


def ai_cli_print_command(cli_tool: str) -> list[str]:
    if ai_cli_kind(cli_tool) == "claude":
        return [cli_tool, "--print"]
    return [cli_tool, "exec", "-"]


def _unique_existing_parent_dirs(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    dirs: list[Path] = []
    for path in paths:
        parent = path.expanduser().parent
        key = parent.resolve() if parent.exists() else parent
        if key in seen:
            continue
        seen.add(key)
        dirs.append(parent)
    return dirs
