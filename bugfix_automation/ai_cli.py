from __future__ import annotations

import shutil
import sys
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


def resolve_ai_cli_tool(cli_tool: str) -> str:
    tool = cli_tool.strip()
    if not tool:
        return tool

    candidate = Path(tool).expanduser()
    if candidate.exists():
        return str(candidate)
    if sys.platform.startswith("win"):
        suffixed = _windows_suffixed_candidate(candidate)
        if suffixed is not None:
            return str(suffixed)
        if candidate.parent != Path("."):
            return tool
        for suffix in (".cmd", ".bat", ".exe"):
            found = shutil.which(f"{tool}{suffix}")
            if found:
                found_path = Path(found)
                if found_path.suffix.lower() == ".exe":
                    cmd_variant = found_path.with_suffix(".cmd")
                    bat_variant = found_path.with_suffix(".bat")
                    if cmd_variant.exists():
                        return str(cmd_variant)
                    if bat_variant.exists():
                        return str(bat_variant)
                return found
        found = shutil.which(tool)
        if found:
            found_path = Path(found)
            if found_path.suffix.lower() == ".exe":
                cmd_variant = found_path.with_suffix(".cmd")
                bat_variant = found_path.with_suffix(".bat")
                if cmd_variant.exists():
                    return str(cmd_variant)
                if bat_variant.exists():
                    return str(bat_variant)
            return found
    return shutil.which(tool) or tool


def _windows_suffixed_candidate(candidate: Path) -> Path | None:
    if candidate.suffix:
        return None
    for suffix in (".exe", ".cmd", ".bat"):
        suffixed = candidate.with_suffix(suffix)
        if suffixed.exists():
            return suffixed
    return None


def ai_log_dir_name(cli_tool: str) -> str:
    kind = ai_cli_kind(cli_tool)
    if kind in {"claude", "codex"}:
        return kind
    stem = Path(cli_tool).stem or "ai"
    return re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-") or "ai"


def ai_cli_command(cli_tool: str, worktree_path: str, prompt: str, image_paths: list[Path] | None = None) -> list[str]:
    executable = resolve_ai_cli_tool(cli_tool)
    if ai_cli_kind(cli_tool) == "claude":
        command = [
            executable,
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
        executable,
        "exec",
        "--dangerously-bypass-approvals-and-sandbox",
        "--cd",
        worktree_path,
    ]
    for image_path in image_paths or []:
        command.extend(["--image", str(image_path)])
    command.append("-")
    return command


def ai_cli_print_command(cli_tool: str) -> list[str]:
    executable = resolve_ai_cli_tool(cli_tool)
    if ai_cli_kind(cli_tool) == "claude":
        return [executable, "--print"]
    return [executable, "exec", "-"]


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
