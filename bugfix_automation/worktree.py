from __future__ import annotations

import subprocess
from pathlib import Path
import shutil
import os


def ensure_worktree(target_repo: Path, worktree_root: Path, branch: str) -> Path:
    worktree_root.mkdir(parents=True, exist_ok=True)
    path = worktree_path_for_branch(worktree_root, branch)
    if path.exists():
        raise FileExistsError(f"Worktree already exists: {path}")
    if branch_exists(target_repo, branch):
        raise FileExistsError(f"Branch already exists: {branch}")
    subprocess.run(["git", "worktree", "add", str(path), "-b", branch], cwd=target_repo, check=True)
    return path


def worktree_path_for_branch(worktree_root: Path, branch: str) -> Path:
    return worktree_root / branch.replace("/", "-")


def branch_exists(target_repo: Path, branch: str) -> bool:
    result = subprocess.run(["git", "rev-parse", "--verify", "--quiet", branch], cwd=target_repo)
    return result.returncode == 0


def branch_worktree_path(target_repo: Path, branch: str) -> Path | None:
    result = subprocess.run(["git", "worktree", "list", "--porcelain"], cwd=target_repo, text=True, capture_output=True, check=True)
    current_path: Path | None = None
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            current_path = Path(line.removeprefix("worktree "))
        elif line == f"branch refs/heads/{branch}" and current_path is not None:
            return current_path
    return None


def install_project_agents(worktree_path: Path, automation_repo: Path) -> None:
    source = automation_repo / ".codex" / "agents"
    if not source.exists():
        return
    target = worktree_path / ".codex" / "agents"
    target.mkdir(parents=True, exist_ok=True)
    for agent_file in source.glob("*.toml"):
        shutil.copy2(agent_file, target / agent_file.name)


def has_app_changes(path: Path, target_app_path: str) -> bool:
    result = subprocess.run(["git", "status", "--porcelain", "--", target_app_path], cwd=path, text=True, capture_output=True, check=True)
    return bool(result.stdout.strip())


def changed_paths(path: Path) -> list[str]:
    result = subprocess.run(["git", "status", "--porcelain"], cwd=path, text=True, capture_output=True, check=True)
    paths: list[str] = []
    for line in result.stdout.splitlines():
        if not line:
            continue
        raw_path = line[3:]
        if " -> " in raw_path:
            raw_path = raw_path.split(" -> ", 1)[1]
        paths.append(raw_path)
    return paths


def out_of_scope_paths(paths: list[str], target_app_path: str) -> list[str]:
    allowed_prefix = target_app_path.rstrip("/") + "/"
    allowed_agent_prefix = ".codex/agents/"
    return [
        path
        for path in paths
        if path != target_app_path.rstrip("/")
        and not path.startswith(allowed_prefix)
        and not path.startswith(allowed_agent_prefix)
    ]


def create_no_push_git_wrapper(worktree_path: Path) -> Path:
    wrapper_dir = worktree_path / ".bugfix-automation-bin"
    wrapper_dir.mkdir(parents=True, exist_ok=True)
    real_git = shutil.which("git") or "/usr/bin/git"
    wrapper = wrapper_dir / "git"
    wrapper.write_text(
        f"""#!/bin/sh
if [ "$1" = "push" ]; then
  echo "git push is disabled by bugfix automation" >&2
  exit 1
fi
exec "{real_git}" "$@"
""",
        encoding="utf-8",
    )
    os.chmod(wrapper, 0o755)
    return wrapper_dir


def install_no_push_hook(worktree_path: Path) -> Path:
    hooks_dir = worktree_path / ".bugfix-automation-hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook = hooks_dir / "pre-push"
    hook.write_text(
        """#!/bin/sh
echo "git push is disabled by bugfix automation" >&2
exit 1
""",
        encoding="utf-8",
    )
    os.chmod(hook, 0o755)
    subprocess.run(
        ["git", "config", "core.hooksPath", str(hooks_dir)],
        cwd=worktree_path,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return hook


def commit_all(path: Path, message: str) -> None:
    subprocess.run(["git", "add", "apps/pc-web"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", message], cwd=path, check=True)
