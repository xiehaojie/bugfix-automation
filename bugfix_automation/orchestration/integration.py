"""Local PR Integration Queue service.

Orchestrates merging multiple fix/* branches into a temporary integration branch,
running verification, and allowing user confirmation before final commit.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from bugfix_automation.config import Config, active_workspace_config
from bugfix_automation.git.runner import git as _git
from bugfix_automation.git.runner import git_rc as _git_rc


INTEGRATION_WORKTREE_ROOT = ".integration-worktrees"
INTEGRATION_RUNS_DIR = "runs/integration-runs"


def _runs_root(config: Config) -> Path:
    return config.runs_root.parent / "runs" / "integration-runs"


def _worktree_root(config: Config) -> Path:
    return config.target_repo.parent / INTEGRATION_WORKTREE_ROOT


def _run_dir(config: Config, run_id: str) -> Path:
    return _runs_root(config) / run_id


def _run_json_path(config: Config, run_id: str) -> Path:
    return _run_dir(config, run_id) / "integration-run.json"


def _generate_run_id(workspace_id: str, target_branch: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    return f"{stamp}-{workspace_id}-{_safe_branch_fragment(target_branch)}"


def _safe_branch_fragment(branch: str) -> str:
    safe = branch.strip().replace("/", "-")
    return "".join(ch for ch in safe if ch.isalnum() or ch in {"-", "_", "."}) or "target"


def _load_run(config: Config, run_id: str) -> dict[str, Any]:
    path = _run_json_path(config, run_id)
    if not path.exists():
        raise FileNotFoundError(f"集成单不存在: {run_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def _save_run(config: Config, run_id: str, data: dict[str, Any]) -> None:
    path = _run_json_path(config, run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now().isoformat()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _branch_has_commits(target_repo: Path, branch: str, base_branch: str) -> bool:
    """Check if a branch has commits beyond the base branch."""
    rc, out, _ = _git_rc(target_repo, ["log", f"{base_branch}..{branch}", "--oneline"])
    return rc == 0 and bool(out.strip())


def _branch_tip_commit(target_repo: Path, branch: str) -> str:
    return _git(target_repo, ["rev-parse", branch])


def _current_branch(target_repo: Path) -> str:
    rc, out, _ = _git_rc(target_repo, ["branch", "--show-current"])
    return out.strip() if rc == 0 and out.strip() else "main"


def _worktree_has_uncommitted(worktree_path: Path) -> bool:
    rc, out, _ = _git_rc(worktree_path, ["status", "--porcelain"])
    return rc == 0 and bool(out.strip())


def _local_branches(target_repo: Path, pattern: str = "refs/heads") -> list[str]:
    rc, out, _ = _git_rc(
        target_repo,
        ["for-each-ref", "--format=%(refname:short)", pattern],
    )
    if rc != 0:
        return []
    return sorted(line.strip() for line in out.splitlines() if line.strip())


# --- Public API ---


def list_runs(config: Config) -> list[dict[str, Any]]:
    """List all integration runs."""
    runs_root = _runs_root(config)
    if not runs_root.exists():
        return []
    runs: list[dict[str, Any]] = []
    for run_dir in sorted(runs_root.iterdir(), reverse=True):
        json_path = run_dir / "integration-run.json"
        if json_path.exists():
            data = json.loads(json_path.read_text(encoding="utf-8"))
            runs.append(data)
    return runs


def get_run(config: Config, run_id: str) -> dict[str, Any]:
    """Get a single integration run by ID."""
    return _load_run(config, run_id)


def create_run(
    config: Config,
    workspace_id: str,
    target_branch: str,
    branches: list[str],
) -> dict[str, Any]:
    """Create a new integration run (draft state)."""
    if not branches:
        raise ValueError("至少需要选择一个 fix 分支")
    if not target_branch:
        raise ValueError("必须指定目标分支")

    run_id = _generate_run_id(workspace_id, target_branch)
    integration_branch = f"integration/{workspace_id}-{_safe_branch_fragment(target_branch)}-{datetime.now().strftime('%Y%m%d-%H%M')}"
    worktree_path = str(_worktree_root(config) / run_id)

    data: dict[str, Any] = {
        "run_id": run_id,
        "workspace_id": workspace_id,
        "target_branch": target_branch,
        "integration_branch": integration_branch,
        "integration_worktree": worktree_path,
        "status": "draft",
        "items": [
            {
                "branch": branch,
                "source_commit": "",
                "apply_method": "",
                "status": "pending",
                "changed_files": [],
                "error": "",
            }
            for branch in branches
        ],
        "verify": {"status": "", "commands": []},
        "ai_review": {"status": "", "summary": ""},
        "final_commit": "",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }

    _save_run(config, run_id, data)
    return data


def start_run(config: Config, run_id: str) -> dict[str, Any]:
    """Start an integration run: create worktree and apply branches."""
    data = _load_run(config, run_id)
    if data["status"] not in ("draft", "blocked", "verify-failed"):
        raise RuntimeError(f"集成单状态为 {data['status']}，不能开始集成")

    data["status"] = "running"
    _save_run(config, run_id, data)

    target_repo = config.target_repo
    target_branch = data["target_branch"]
    integration_branch = data["integration_branch"]
    worktree_path = Path(data["integration_worktree"])

    # Create integration worktree from target branch
    if worktree_path.exists():
        # Remove existing worktree to start fresh
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(worktree_path)],
            cwd=target_repo, capture_output=True,
        )
    # Delete old integration branch if exists
    subprocess.run(
        ["git", "branch", "-D", integration_branch],
        cwd=target_repo, capture_output=True,
    )

    worktree_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "worktree", "add", str(worktree_path), "-b", integration_branch, target_branch],
        cwd=target_repo, check=True,
    )

    # Apply each fix branch
    workspace = active_workspace_config(config)
    target_app_path = workspace.target_app_path if workspace else config.target_app_path

    for item in data["items"]:
        branch = item["branch"]
        item["status"] = "applying"
        _save_run(config, run_id, data)

        try:
            applied = _apply_branch(
                target_repo, worktree_path, branch, target_branch, target_app_path
            )
            item["source_commit"] = applied["source_commit"]
            item["apply_method"] = applied["apply_method"]
            item["changed_files"] = applied["changed_files"]
            item["status"] = "applied"
            item["error"] = ""
        except Exception as exc:
            item["status"] = "conflict"
            item["error"] = str(exc)
            # Abort the current application to restore clean state
            subprocess.run(
                ["git", "checkout", "--", "."],
                cwd=worktree_path, capture_output=True,
            )
            data["status"] = "blocked"
            _save_run(config, run_id, data)
            return data

    _save_run(config, run_id, data)

    data["verify"] = {"status": "ai-verified", "commands": []}
    data["status"] = "pending-user-approval"

    _save_run(config, run_id, data)
    return data


def confirm_run(config: Config, run_id: str) -> dict[str, Any]:
    """User confirms integration — create final commit."""
    data = _load_run(config, run_id)
    if data["status"] not in ("pending-user-approval", "verify-failed"):
        raise RuntimeError(f"集成单状态为 {data['status']}，不能确认提交")

    worktree_path = Path(data["integration_worktree"])
    if not worktree_path.exists():
        raise RuntimeError("集成 worktree 不存在，无法提交")

    workspace = active_workspace_config(config)
    target_app_path = workspace.target_app_path if workspace else config.target_app_path

    # Stage only changes inside the configured app path.
    subprocess.run(["git", "add", target_app_path], cwd=worktree_path, check=True)
    if not _has_staged_changes(worktree_path, target_app_path):
        raise RuntimeError("没有可提交的集成改动，不能确认提交")

    # Build commit message
    applied_branches = [item for item in data["items"] if item["status"] == "applied"]
    scope = target_app_path.rstrip("/").split("/")[-1] or "frontend"
    lines = [f"fix({scope}): batch apply AI bug fixes", ""]
    lines.append("Included fixes:")
    for item in applied_branches:
        commit_info = f" ({item['source_commit'][:7]})" if item["source_commit"] else ""
        lines.append(f"- {item['branch']}{commit_info}")
    lines.append("")
    lines.append(f"Integration run: {data['run_id']}")
    verify_status = data.get("verify", {}).get("status", "unknown")
    lines.append(f"Verified: {verify_status}")
    commit_message = "\n".join(lines)

    subprocess.run(
        ["git", "commit", "-m", commit_message],
        cwd=worktree_path, check=True,
    )
    commit_sha = _git(worktree_path, ["rev-parse", "HEAD"])

    data["final_commit"] = commit_sha
    data["status"] = "committed"
    _save_run(config, run_id, data)

    # Write markdown report
    _write_markdown_report(config, run_id, data)

    return data


def cleanup_run(config: Config, run_id: str) -> dict[str, Any]:
    """Delete successfully applied fix branches and worktrees."""
    data = _load_run(config, run_id)
    if data["status"] != "committed":
        raise RuntimeError(f"集成单状态为 {data['status']}，只有已提交的集成单才能清理")
    if not data.get("final_commit"):
        raise RuntimeError("没有 final_commit，不能清理来源分支")

    target_repo = config.target_repo
    worktree_root = config.worktree_root
    cleaned_branches: list[str] = []

    for item in data["items"]:
        if item["status"] != "applied":
            continue
        branch = item["branch"]
        if not branch.startswith("fix/"):
            continue

        # Remove worktree
        from bugfix_automation.git.worktree import worktree_path_for_branch

        wt_path = worktree_path_for_branch(worktree_root, branch)
        if wt_path.exists():
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(wt_path)],
                cwd=target_repo, capture_output=True,
            )

        # Delete branch
        subprocess.run(
            ["git", "branch", "-D", branch],
            cwd=target_repo, capture_output=True,
        )
        cleaned_branches.append(branch)

    data["status"] = "cleaned"
    data["cleaned_branches"] = cleaned_branches
    _save_run(config, run_id, data)
    return data


def abort_run(config: Config, run_id: str) -> dict[str, Any]:
    """Abort integration: remove integration worktree and branch, keep fix branches."""
    data = _load_run(config, run_id)
    if data["status"] in ("committed", "cleaned"):
        raise RuntimeError(f"集成单状态为 {data['status']}，已提交的集成单不能中止")

    _remove_integration_artifacts(config, data)

    data["status"] = "aborted"
    _save_run(config, run_id, data)
    return data


def delete_run(config: Config, run_id: str) -> dict[str, Any]:
    """Delete an integration run record and its integration artifacts.

    This never deletes source fix/* branches. Use cleanup_run for source branch cleanup
    after the user has confirmed a final integration commit.
    """
    data = _load_run(config, run_id)
    if data["status"] == "running":
        raise RuntimeError("集成单正在执行中，不能删除")

    _remove_integration_artifacts(config, data)
    run_dir = _run_dir(config, run_id)
    if run_dir.exists():
        shutil.rmtree(run_dir)
    return {"run_id": run_id, "deleted": True}


def available_fix_branches(config: Config) -> list[dict[str, Any]]:
    """List fix/* branches available for integration."""
    from bugfix_automation.git.worktree import branch_worktree_path, worktree_path_for_branch

    branches: list[dict[str, Any]] = []
    for branch in _local_branches(config.target_repo, "refs/heads/fix"):
        worktree_path = branch_worktree_path(config.target_repo, branch)
        inferred_path = worktree_path_for_branch(config.worktree_root, branch)
        has_worktree = worktree_path is not None or inferred_path.exists()
        display_path = (worktree_path or inferred_path) if has_worktree else None
        branches.append({
            "branch": branch,
            "path": str(display_path or ""),
            "has_worktree": has_worktree,
            "source_commit": _branch_tip_commit(config.target_repo, branch),
        })
    return branches


def target_branches(config: Config) -> dict[str, Any]:
    """List local branches that can be used as integration targets."""
    branches = [
        branch
        for branch in _local_branches(config.target_repo)
        if not branch.startswith("fix/") and not branch.startswith("integration/")
    ]
    current = _current_branch(config.target_repo)
    if current not in branches:
        branches.insert(0, current)
    return {"current": current, "branches": branches, "workspace_id": config.active_workspace}


def _remove_integration_artifacts(config: Config, data: dict[str, Any]) -> None:
    target_repo = config.target_repo
    worktree_path = Path(data["integration_worktree"])
    integration_branch = data["integration_branch"]

    if worktree_path.exists():
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(worktree_path)],
            cwd=target_repo, capture_output=True,
        )

    subprocess.run(
        ["git", "branch", "-D", integration_branch],
        cwd=target_repo, capture_output=True,
    )


def get_run_diff(config: Config, run_id: str) -> str:
    """Get cumulative diff for an integration run."""
    data = _load_run(config, run_id)
    worktree_path = Path(data["integration_worktree"])
    if not worktree_path.exists():
        return ""
    target_branch = data["target_branch"]
    workspace = active_workspace_config(config)
    target_app_path = workspace.target_app_path if workspace else config.target_app_path
    rc, out, _ = _git_rc(
        worktree_path,
        ["diff", target_branch, "--", target_app_path],
    )
    return out if rc == 0 else ""


# --- Internal helpers ---


def _apply_branch(
    target_repo: Path,
    worktree_path: Path,
    branch: str,
    base_branch: str,
    target_app_path: str,
) -> dict[str, Any]:
    """Apply a fix branch to the integration worktree."""
    has_commits = _branch_has_commits(target_repo, branch, base_branch)

    if has_commits:
        # Use cherry-pick -n for branches with commits
        commit = _branch_tip_commit(target_repo, branch)
        changed_files = _commit_changed_files(target_repo, commit, target_app_path)
        rc, out, err = _git_rc(worktree_path, ["cherry-pick", "-n", commit])
        if rc != 0:
            # Try to abort cherry-pick
            subprocess.run(
                ["git", "cherry-pick", "--abort"],
                cwd=worktree_path, capture_output=True,
            )
            raise RuntimeError(f"cherry-pick 冲突: {err}")
        return {
            "source_commit": commit,
            "apply_method": "cherry-pick-no-commit",
            "changed_files": changed_files,
        }
    else:
        # Use git diff from the fix worktree and apply
        from bugfix_automation.git.worktree import worktree_path_for_branch, branch_worktree_path

        fix_wt = branch_worktree_path(target_repo, branch)
        if fix_wt is None:
            fix_wt = worktree_path_for_branch(config_worktree_root(target_repo), branch)

        if fix_wt is None or not fix_wt.exists():
            raise RuntimeError(f"找不到分支 {branch} 对应的 worktree")

        # Generate diff from the fix worktree
        rc, diff_output, _ = _git_rc(
            fix_wt,
            ["diff", "--binary", "--", target_app_path],
        )
        if rc != 0 or not diff_output.strip():
            raise RuntimeError(f"分支 {branch} 没有可应用的改动")

        # Apply diff
        apply_proc = subprocess.run(
            ["git", "apply", "--3way"],
            input=diff_output, text=True,
            cwd=worktree_path, capture_output=True,
        )
        if apply_proc.returncode != 0:
            raise RuntimeError(f"git apply 失败: {apply_proc.stderr}")

        # Stage changes
        subprocess.run(["git", "add", target_app_path], cwd=worktree_path, check=True)
        changed_files = _worktree_changed_files(fix_wt, target_app_path)
        return {
            "source_commit": "",
            "apply_method": "diff-apply-3way",
            "changed_files": changed_files,
        }


def config_worktree_root(target_repo: Path) -> Path:
    """Infer worktree root from config - fallback helper."""
    from bugfix_automation.config import load_config

    cfg = load_config()
    return cfg.worktree_root


def _staged_files(worktree_path: Path) -> list[str]:
    """Get list of staged files."""
    rc, out, _ = _git_rc(worktree_path, ["diff", "--cached", "--name-only"])
    if rc != 0:
        return []
    return [f for f in out.splitlines() if f.strip()]


def _has_staged_changes(worktree_path: Path, target_app_path: str) -> bool:
    rc, out, _ = _git_rc(worktree_path, ["diff", "--cached", "--name-only", "--", target_app_path])
    return rc == 0 and bool(out.strip())


def _commit_changed_files(target_repo: Path, commit: str, target_app_path: str) -> list[str]:
    rc, out, _ = _git_rc(
        target_repo,
        ["diff-tree", "--no-commit-id", "--name-only", "-r", commit, "--", target_app_path],
    )
    if rc != 0:
        return []
    return sorted(line.strip() for line in out.splitlines() if line.strip())


def _worktree_changed_files(worktree_path: Path, target_app_path: str) -> list[str]:
    rc, out, _ = _git_rc(worktree_path, ["status", "--porcelain", "--", target_app_path])
    if rc != 0:
        return []
    automation_prefixes = (".codex/", ".claude/", ".bugfix-automation-bin/")
    files: list[str] = []
    for line in out.splitlines():
        raw_path = line[3:]
        if " -> " in raw_path:
            raw_path = raw_path.split(" -> ", 1)[1]
        if raw_path and not raw_path.startswith(automation_prefixes):
            files.append(raw_path)
    return sorted(files)


def _write_markdown_report(config: Config, run_id: str, data: dict[str, Any]) -> None:
    """Write a human-readable markdown report for the integration run."""
    run_dir = _run_dir(config, run_id)
    md_path = run_dir / "integration-report.md"

    lines = [
        f"# 集成报告: {run_id}",
        "",
        f"- 目标分支: `{data['target_branch']}`",
        f"- 集成分支: `{data['integration_branch']}`",
        f"- 状态: {data['status']}",
        f"- Final Commit: `{data.get('final_commit', '')}`",
        f"- 创建时间: {data['created_at']}",
        f"- 更新时间: {data['updated_at']}",
        "",
        "## 应用结果",
        "",
        "| 分支 | 方式 | 状态 | 错误 |",
        "|------|------|------|------|",
    ]
    for item in data["items"]:
        lines.append(
            f"| `{item['branch']}` | {item['apply_method']} | {item['status']} | {item.get('error', '')} |"
        )
    lines.append("")

    ai_review = data.get("ai_review", {})
    if ai_review.get("summary"):
        lines.append("## AI 复核")
        lines.append("")
        lines.append(ai_review["summary"])
        lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")
