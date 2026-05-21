from __future__ import annotations

import subprocess
from pathlib import Path
import shutil
import os


def ensure_worktree(target_repo: Path, worktree_root: Path, branch: str) -> Path:
    worktree_root.mkdir(parents=True, exist_ok=True)
    path = worktree_path_for_branch(worktree_root, branch)
    if path.exists():
        raise FileExistsError(f"worktree 已存在：{path}")
    if branch_exists(target_repo, branch):
        raise FileExistsError(f"分支已存在：{branch}")
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


def rename_current_branch(path: Path, next_branch: str) -> None:
    subprocess.run(["git", "branch", "-m", next_branch], cwd=path, check=True)


def install_project_agents(worktree_path: Path, automation_repo: Path) -> None:
    source = automation_repo / ".codex" / "agents"
    if not source.exists():
        return
    target = worktree_path / ".codex" / "agents"
    target.mkdir(parents=True, exist_ok=True)
    for agent_file in source.glob("*.toml"):
        shutil.copy2(agent_file, target / agent_file.name)


def symlink_node_modules(worktree_path: Path, target_repo: Path) -> None:
    """Symlink node_modules from the main repo into the worktree so npm/build works."""
    src = target_repo / "node_modules"
    dst = worktree_path / "node_modules"
    if src.exists() and not dst.exists():
        dst.symlink_to(src)
    # Also handle workspace packages one level deep (e.g. apps/*/node_modules, packages/*/node_modules)
    for category in ("apps", "packages", "libs"):
        category_dir = target_repo / category
        if not category_dir.is_dir():
            continue
        for pkg_dir in category_dir.iterdir():
            nm = pkg_dir / "node_modules"
            if nm.is_dir():
                dst_nm = worktree_path / category / pkg_dir.name / "node_modules"
                if not dst_nm.exists():
                    dst_nm.symlink_to(nm)


def has_app_changes(path: Path, target_app_path: str) -> bool:
    result = subprocess.run(["git", "status", "--porcelain", "--", target_app_path], cwd=path, text=True, capture_output=True, check=True)
    return bool(result.stdout.strip())


def tracked_changed_files(path: Path, target_app_path: str) -> list[str]:
    result = subprocess.run(["git", "status", "--porcelain", "--", target_app_path], cwd=path, text=True, capture_output=True, check=True)
    automation_prefixes = (".codex/", ".bugfix-automation-bin/")
    files: list[str] = []
    for line in result.stdout.splitlines():
        raw_path = line[3:]
        if " -> " in raw_path:
            raw_path = raw_path.split(" -> ", 1)[1]
        if raw_path and not raw_path.startswith(automation_prefixes):
            files.append(raw_path)
    return sorted(files)


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
    # "." or empty means the entire repo is the target — nothing is out of scope
    if target_app_path.strip().strip("/") in ("", "."):
        return []
    allowed_prefix = target_app_path.rstrip("/") + "/"
    allowed_automation_paths = (".codex/", ".bugfix-automation-bin/")
    return [
        path
        for path in paths
        if path != target_app_path.rstrip("/")
        and not path.startswith(allowed_prefix)
        and not path.startswith(allowed_automation_paths)
    ]


def write_worktree_exclude(worktree_path: Path) -> None:
    """Add automation-only directories to the worktree's local git exclude list."""
    git_file = worktree_path / ".git"
    if not git_file.is_file():
        return
    content = git_file.read_text(encoding="utf-8").strip()
    if not content.startswith("gitdir:"):
        return
    git_dir_str = content.removeprefix("gitdir:").strip()
    git_dir = Path(git_dir_str) if Path(git_dir_str).is_absolute() else (worktree_path / git_dir_str).resolve()
    info_dir = git_dir / "info"
    info_dir.mkdir(parents=True, exist_ok=True)
    exclude_file = info_dir / "exclude"
    existing = exclude_file.read_text(encoding="utf-8") if exclude_file.exists() else ""
    entries = ""
    if ".bugfix-automation-bin" not in existing:
        entries += ".bugfix-automation-bin\n"
    if ".codex" not in existing:
        entries += ".codex\n"
    if entries:
        with exclude_file.open("a", encoding="utf-8") as f:
            f.write(entries)


def create_no_push_git_wrapper(worktree_path: Path) -> Path:
    wrapper_dir = worktree_path / ".bugfix-automation-bin"
    wrapper_dir.mkdir(parents=True, exist_ok=True)
    real_git = shutil.which("git") or "/usr/bin/git"
    wrapper = wrapper_dir / "git"
    wrapper.write_text(
        f"""#!/bin/sh
if [ "$1" = "push" ]; then
  echo "自动修复流程已禁止 git push" >&2
  exit 1
fi
exec "{real_git}" "$@"
""",
        encoding="utf-8",
    )
    os.chmod(wrapper, 0o755)
    return wrapper_dir


def commit_all(path: Path, message: str, target_app_path: str = "apps/pc-web") -> str:
    subprocess.run(["git", "add", target_app_path], cwd=path, check=True)
    subprocess.run(["git", "commit", "-m", message], cwd=path, check=True)
    return head_sha(path)


def head_sha(path: Path) -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=path, text=True, capture_output=True, check=True)
    return result.stdout.strip()


def diff_stat(path: Path, base: str, head: str, target_app_path: str = "apps/pc-web") -> str:
    result = subprocess.run(["git", "diff", "--stat", base, head, "--", target_app_path], cwd=path, text=True, capture_output=True, check=True)
    return result.stdout.strip()
