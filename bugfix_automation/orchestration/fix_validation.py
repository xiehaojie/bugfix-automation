from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from bugfix_automation.config import Config, active_workspace_config
from bugfix_automation.git.runner import git as _git
from bugfix_automation.git.runner import git_rc as _git_rc
from bugfix_automation.git.runner import run_git as _run_git
from bugfix_automation.git.runner import run_git_quiet as _run_git_quiet
from bugfix_automation.storage.repositories import create_operation
from bugfix_automation.domain.task_state import task_state
from bugfix_automation.git.worktree import branch_worktree_path, worktree_path_for_branch, write_worktree_exclude

VALIDATION_RUNS_DIR = "fix-validations"
VALIDATION_WORKTREE_ROOT = ".validation-worktrees"


def get_validation(config: Config, branch: str) -> dict[str, Any]:
    _validate_fix_branch(config, branch)
    path = _validation_json_path(config, branch)
    if not path.exists():
        return _new_validation(config, branch)
    data = json.loads(path.read_text(encoding="utf-8"))
    _ensure_validation_matches_branch(data, branch)
    return data


def verify(config: Config, branch: str, *, commands_override: list[list[str]] | None = None) -> dict[str, Any]:
    """Create a merge preview for a fix branch and trust the AI's own verification."""
    _validate_fix_branch(config, branch)

    with _validation_lock(config, branch):
        data = get_validation(config, branch)
        if data["status"] in {"committed", "cleaned"}:
            raise RuntimeError(f"预演单状态为 {data['status']}，不能重新预演")

        data["status"] = "verifying"
        data["error"] = ""
        data["verify"] = {"status": "ai-verified", "commands": []}
        _save_validation(config, branch, data)

        workspace = active_workspace_config(config)
        target_repo = workspace.target_repo if workspace else config.target_repo
        _ensure_local_branch(target_repo, branch)
        target_branch = data["target_branch"]
        worktree_path = Path(data["integration_worktree"])
        integration_branch = data["integration_branch"]

        with _repo_lock(config):
            _remove_preview_artifacts(config, target_repo, worktree_path, integration_branch)
            worktree_path.parent.mkdir(parents=True, exist_ok=True)
            _run_git(target_repo, ["worktree", "add", str(worktree_path), "-b", integration_branch, target_branch])
        write_worktree_exclude(worktree_path)

        target_app_path = workspace.target_app_path if workspace else config.target_app_path
        try:
            applied = _apply_branch(config, target_repo, worktree_path, branch, target_branch, target_app_path)
        except RuntimeError as exc:
            _run_git_quiet(worktree_path, ["cherry-pick", "--abort"])
            data["status"] = "conflict"
            data["error"] = str(exc)
            _save_validation(config, branch, data)
            _record_validation_op(config, "fix-preview", "conflict", branch, data)
            return data

        data.update(applied)
        data["changed_files"] = applied["changed_files"]
        data["verify"] = {"status": "ai-verified", "commands": []}
        data["status"] = "ready-to-commit"
        _save_validation(config, branch, data)
        _record_validation_op(config, "fix-preview", "ready-to-commit", branch, data)
        return data


def commit_validation(config: Config, branch: str, location: str) -> dict[str, Any]:
    if location not in {"integration", "target"}:
        raise ValueError("提交位置只能是 integration 或 target")

    _validate_fix_branch(config, branch)
    with _validation_lock(config, branch):
        data = get_validation(config, branch)
        if data["status"] not in {"ready-to-commit", "ai-review-needed"}:
            raise RuntimeError(f"验证单状态为 {data['status']}，不能提交")

        workspace = active_workspace_config(config)
        target_repo = workspace.target_repo if workspace else config.target_repo
        target_app_path = workspace.target_app_path if workspace else config.target_app_path
        worktree_path = Path(data["integration_worktree"])
        if not worktree_path.exists():
            raise RuntimeError("预演 worktree 不存在，无法提交")

        commit_cwd = worktree_path
        if location == "target":
            with _repo_lock(config):
                _ensure_target_branch(config, target_repo, data["target_branch"])
                if _has_uncommitted_changes(target_repo):
                    raise RuntimeError("目标分支工作区不干净，不能直接提交到目标分支")
                _apply_preview_to_target(target_repo, worktree_path, target_app_path)
                _run_git(target_repo, ["add", target_app_path])
                if not _has_staged_changes(target_repo, target_app_path):
                    raise RuntimeError("没有可提交的修复改动")
                _run_git(target_repo, ["commit", "-m", _commit_message(data, target_app_path)])
                commit_sha = _git(target_repo, ["rev-parse", "HEAD"]).strip()
        else:
            _run_git(commit_cwd, ["add", target_app_path])
            if not _has_staged_changes(commit_cwd, target_app_path):
                raise RuntimeError("没有可提交的修复改动")
            _run_git(commit_cwd, ["commit", "-m", _commit_message(data, target_app_path)])
            commit_sha = _git(commit_cwd, ["rev-parse", "HEAD"]).strip()

        data["status"] = "committed"
        data["final_commit"] = commit_sha
        data["final_commit_location"] = location
        _save_validation(config, branch, data)

        # 入库记录此次提交
        _record_commit_op(config, branch, commit_sha, location, data)

        if location == "target":
            # target 提交后，integration worktree/branch 和 fix worktree/branch 均可清理
            try:
                _remove_preview_artifacts(config, target_repo, worktree_path, data["integration_branch"])
            except Exception:
                pass
            try:
                fix_wt = branch_worktree_path(target_repo, branch) or worktree_path_for_branch(config.worktree_root, branch)
                if fix_wt.exists():
                    _run_git_quiet(target_repo, ["worktree", "remove", "--force", str(fix_wt)])
                _run_git_quiet(target_repo, ["branch", "-D", branch])
            except Exception:
                pass
        else:
            # integration 提交后：仅移除 worktree 目录（节省磁盘），保留 integration_branch 和 fix branch
            # 保留分支使 monorepo 中可看到提交记录，且 revert/undo 仍可操作
            try:
                if worktree_path.exists():
                    _run_git_quiet(target_repo, ["worktree", "remove", "--force", str(worktree_path)])
                    shutil.rmtree(worktree_path, ignore_errors=True)
            except Exception:
                pass

        return data


def merge_validation_to_target(config: Config, branch: str) -> dict[str, Any]:
    """Apply an integration-branch validation commit onto the target branch."""
    _validate_fix_branch(config, branch)
    with _validation_lock(config, branch):
        data = get_validation(config, branch)
        if data["status"] != "committed" or not data.get("final_commit"):
            raise RuntimeError("只有已提交到临时集成分支的验证单才能合并到目标分支")
        if data.get("final_commit_location") == "target":
            raise RuntimeError("此修复已经在目标分支上，无需重复合并")
        if data.get("final_commit_location") not in {"", "integration"}:
            raise RuntimeError(f"不支持的提交位置：{data.get('final_commit_location')}")

        workspace = active_workspace_config(config)
        target_repo = workspace.target_repo if workspace else config.target_repo
        original_commit = data["final_commit"]

        with _repo_lock(config):
            _ensure_target_branch(config, target_repo, data["target_branch"])
            if _has_uncommitted_changes(target_repo):
                raise RuntimeError("目标分支工作区不干净，不能合并")
            rc, _, err = _git_rc(target_repo, ["cherry-pick", original_commit])
            if rc != 0:
                _run_git_quiet(target_repo, ["cherry-pick", "--abort"])
                raise RuntimeError(f"合并到目标分支失败: {err}")
            target_commit = _git(target_repo, ["rev-parse", "HEAD"]).strip()

            try:
                _remove_preview_artifacts(
                    config,
                    target_repo,
                    Path(data["integration_worktree"]),
                    data["integration_branch"],
                )
            except Exception:
                pass

        data["final_commit"] = target_commit
        data["final_commit_location"] = "target"
        data["merged_from_integration_commit"] = original_commit
        data["merged_to_target_at"] = datetime.now().isoformat()
        _save_validation(config, branch, data)
        _record_validation_op(config, "fix-merge-target", "committed", branch, data)
        return data


def revert_validation(config: Config, branch: str) -> dict[str, Any]:
    _validate_fix_branch(config, branch)
    with _validation_lock(config, branch):
        data = get_validation(config, branch)
        if data["status"] != "committed" or not data.get("final_commit"):
            raise RuntimeError("只有已提交的验证单才能撤回")

        workspace = active_workspace_config(config)
        target_repo = workspace.target_repo if workspace else config.target_repo
        location = data.get("final_commit_location") or "integration"
        cwd = Path(data["integration_worktree"]) if location == "integration" else target_repo
        if location == "target":
            with _repo_lock(config):
                _ensure_target_branch(config, target_repo, data["target_branch"])
                if not cwd.exists():
                    raise RuntimeError("提交所在 worktree 不存在，不能撤回")
                if _has_uncommitted_changes(cwd):
                    raise RuntimeError("提交所在工作区不干净，不能撤回")
                _run_git(cwd, ["revert", "--no-edit", data["final_commit"]])
                data["revert_commit"] = _git(cwd, ["rev-parse", "HEAD"]).strip()
        else:
            integration_branch = data["integration_branch"]
            _temp_created = False
            if not cwd.exists():
                # worktree 已被清理，临时重建以执行 revert
                cwd.parent.mkdir(parents=True, exist_ok=True)
                _run_git(target_repo, ["worktree", "add", str(cwd), integration_branch])
                _temp_created = True
            if _has_uncommitted_changes(cwd):
                if _temp_created:
                    _run_git_quiet(target_repo, ["worktree", "remove", "--force", str(cwd)])
                raise RuntimeError("提交所在工作区不干净，不能撤回")
            _run_git(cwd, ["revert", "--no-edit", data["final_commit"]])
            data["revert_commit"] = _git(cwd, ["rev-parse", "HEAD"]).strip()
            # 撤回后移除 worktree 目录，保留分支（分支含撤回 commit，monorepo 中可见）
            try:
                _run_git_quiet(target_repo, ["worktree", "remove", "--force", str(cwd)])
                shutil.rmtree(cwd, ignore_errors=True)
            except Exception:
                pass

        data["status"] = "reverted"
        _save_validation(config, branch, data)
        _record_validation_op(config, "fix-revert", "reverted", branch, data)
        return data


def undo_commit(config: Config, branch: str) -> dict[str, Any]:
    """撤销上次提交（git reset --soft HEAD~1），改动保留在暂存区。

    类似 VS Code 的「撤销上次提交」，直接移除 commit 而非生成反向提交。
    仅当该 commit 是目标分支最新提交时才可执行。
    """
    _validate_fix_branch(config, branch)
    with _validation_lock(config, branch):
        data = get_validation(config, branch)
        if data["status"] != "committed" or not data.get("final_commit"):
            raise RuntimeError("只有已提交的验证单才能撤销")

        workspace = active_workspace_config(config)
        target_repo = workspace.target_repo if workspace else config.target_repo
        location = data.get("final_commit_location") or "integration"
        cwd = Path(data["integration_worktree"]) if location == "integration" else target_repo

        with _repo_lock(config):
            if location == "target":
                _ensure_target_branch(config, target_repo, data["target_branch"])
            _temp_created = False
            if not cwd.exists():
                if location == "integration":
                    # worktree 已被清理，临时重建以执行 reset
                    cwd.parent.mkdir(parents=True, exist_ok=True)
                    _run_git(target_repo, ["worktree", "add", str(cwd), data["integration_branch"]])
                    _temp_created = True
                else:
                    raise RuntimeError("提交所在仓库不存在")
            # 验证 HEAD 确实是我们的提交
            current_head = _git(cwd, ["rev-parse", "HEAD"]).strip()
            if current_head != data["final_commit"]:
                if _temp_created:
                    _run_git_quiet(target_repo, ["worktree", "remove", "--force", str(cwd)])
                raise RuntimeError(
                    f"当前 HEAD ({current_head[:8]}) 不是此修复的提交 ({data['final_commit'][:8]})，"
                    "可能有新提交在其之上，不能安全撤销。请用「撤回此提交」(revert) 代替。"
                )
            _run_git(cwd, ["reset", "--soft", "HEAD~1"])
            if _temp_created:
                try:
                    _run_git_quiet(target_repo, ["worktree", "remove", "--force", str(cwd)])
                    shutil.rmtree(cwd, ignore_errors=True)
                except Exception:
                    pass

        data["status"] = "ready-to-commit"
        data.pop("final_commit", None)
        data.pop("final_commit_location", None)
        _save_validation(config, branch, data)
        _record_validation_op(config, "fix-undo-commit", "ready-to-commit", branch, data)
        return data


def remove_preview(config: Config, branch: str) -> dict[str, Any]:
    _validate_fix_branch(config, branch)
    with _validation_lock(config, branch):
        data = get_validation(config, branch)
        if data["status"] == "committed":
            raise RuntimeError("已提交的验证单不能移除预演，请先撤回提交")
        if data["status"] == "cleaned":
            raise RuntimeError("已清理的验证单不能移除预演")

        workspace = active_workspace_config(config)
        target_repo = workspace.target_repo if workspace else config.target_repo
        with _repo_lock(config):
            _remove_preview_artifacts(config, target_repo, Path(data["integration_worktree"]), data["integration_branch"])
        data["status"] = "preview-removed"
        _save_validation(config, branch, data)
        _record_validation_op(config, "fix-remove-preview", "preview-removed", branch, data)
        return data


def discard_preview_for_source_branch(config: Config, branch: str) -> None:
    """Remove any uncommitted preview branch/worktree tied to a rejected fix branch."""
    _validate_fix_branch(config, branch)
    path = _validation_json_path(config, branch)
    if not path.exists():
        return
    with _validation_lock(config, branch):
        if not path.exists():
            return
        data = get_validation(config, branch)
        if data.get("status") == "committed":
            return

        workspace = active_workspace_config(config) if config.workspaces else None
        target_repo = workspace.target_repo if workspace else config.target_repo
        with _repo_lock(config):
            _remove_preview_artifacts(
                config,
                target_repo,
                Path(data["integration_worktree"]),
                data["integration_branch"],
            )
        data["status"] = "preview-removed"
        _save_validation(config, branch, data)


def cleanup_source(config: Config, branch: str) -> dict[str, Any]:
    _validate_fix_branch(config, branch)
    with _validation_lock(config, branch):
        data = get_validation(config, branch)
        if data["status"] not in {"committed", "reverted"}:
            raise RuntimeError("只有已提交或已撤回的验证单才能清理来源分支")

        workspace = active_workspace_config(config)
        target_repo = workspace.target_repo if workspace else config.target_repo
        with _repo_lock(config):
            fix_wt = branch_worktree_path(target_repo, branch) or worktree_path_for_branch(config.worktree_root, branch)
            if fix_wt.exists():
                allowed_roots = (config.worktree_root, target_repo.parent / VALIDATION_WORKTREE_ROOT)
                _ensure_child_path(fix_wt, allowed_roots)
                _run_git_quiet(target_repo, ["worktree", "remove", "--force", str(fix_wt)])
            _ensure_local_branch(target_repo, branch)
            _run_git_quiet(target_repo, ["branch", "-D", branch])

        data["status"] = "cleaned"
        data["cleaned_branch"] = branch
        _save_validation(config, branch, data)
        _record_validation_op(config, "fix-cleanup-source", "cleaned", branch, data)
        return data


def _new_validation(config: Config, branch: str) -> dict[str, Any]:
    workspace = active_workspace_config(config)
    target_repo = workspace.target_repo if workspace else config.target_repo
    target_branch = _current_branch(target_repo)
    safe_branch = _safe_branch_fragment(branch)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    run_id = f"{safe_branch}-{stamp}"
    return {
        "branch": branch,
        "run_id": run_id,
        "target_branch": target_branch,
        "integration_branch": f"integration/{safe_branch}-{stamp}",
        "integration_worktree": str(_worktree_root(config) / run_id),
        "status": "pending",
        "apply_method": "",
        "source_commit": "",
        "changed_files": [],
        "verify": {"status": "", "commands": []},
        "ai_review": {"status": "", "summary": ""},
        "final_commit": "",
        "final_commit_location": "",
        "revert_commit": "",
        "error": "",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }


def _validation_root(config: Config) -> Path:
    return config.runs_root.parent / "runs" / VALIDATION_RUNS_DIR


def _validation_dir(config: Config, branch: str) -> Path:
    return _validation_root(config) / _safe_branch_fragment(branch)


def _validation_lock_path(config: Config, branch: str) -> Path:
    return _validation_dir(config, branch) / ".lock"


def _repo_lock_path(config: Config) -> Path:
    return _validation_root(config) / ".target-repo.lock"


def _acquire_lock(path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        return os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError("已有 Git 操作正在进行，请稍后重试") from exc


@contextmanager
def _validation_lock(config: Config, branch: str) -> Iterator[None]:
    path = _validation_lock_path(config, branch)
    fd = _acquire_lock(path)
    try:
        os.close(fd)
        yield
    finally:
        path.unlink(missing_ok=True)


@contextmanager
def _repo_lock(config: Config) -> Iterator[None]:
    path = _repo_lock_path(config)
    fd = _acquire_lock(path)
    try:
        os.close(fd)
        yield
    finally:
        path.unlink(missing_ok=True)


def _validation_json_path(config: Config, branch: str) -> Path:
    return _validation_dir(config, branch) / "validation.json"


def _worktree_root(config: Config) -> Path:
    workspace = active_workspace_config(config)
    target_repo = workspace.target_repo if workspace else config.target_repo
    return target_repo.parent / VALIDATION_WORKTREE_ROOT


def _save_validation(config: Config, branch: str, data: dict[str, Any]) -> None:
    path = _validation_json_path(config, branch)
    path.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now().isoformat()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_branch_fragment(branch: str) -> str:
    safe = branch.strip().replace("/", "-")
    fragment = "".join(ch for ch in safe if ch.isalnum() or ch in {"-", "_", "."}) or "branch"
    digest = hashlib.sha256(branch.encode("utf-8")).hexdigest()[:10]
    return f"{fragment}-{digest}"


def _validate_fix_branch(config: Config, branch: str) -> None:
    if not branch.startswith("fix/"):
        raise ValueError("只能验证 fix/* 分支")
    if ".." in branch or branch.startswith("/") or branch.endswith("/"):
        raise ValueError("分支名称不合法")
    rc, _, _ = _git_rc(config.target_repo, ["check-ref-format", "--branch", branch])
    if rc != 0:
        raise ValueError("分支名称不合法")


def _ensure_validation_matches_branch(data: dict[str, Any], branch: str) -> None:
    if data.get("branch") != branch:
        raise RuntimeError("验证单分支与请求分支不一致")


def _ensure_target_branch(config: Config, target_repo: Path, target_branch: str) -> None:
    _ensure_allowed_target_branch(config, target_branch)
    current = _current_branch(target_repo)
    if current != target_branch:
        raise RuntimeError(f"目标仓库当前分支为 {current}，不是验证时的 {target_branch}")


def _ensure_allowed_target_branch(config: Config, target_branch: str) -> None:
    if target_branch not in config.validation_target_branches:
        raise RuntimeError(f"目标分支不允许直接提交：{target_branch}")


def _ensure_local_branch(target_repo: Path, branch: str) -> None:
    rc, _, _ = _git_rc(target_repo, ["show-ref", "--verify", f"refs/heads/{branch}"])
    if rc != 0:
        raise RuntimeError(f"本地分支不存在：{branch}")


def _ensure_child_path(path: Path, roots: tuple[Path, ...]) -> None:
    resolved_path = path.resolve()
    resolved_roots = tuple(root.resolve() for root in roots)
    if any(resolved_path != root and root in resolved_path.parents for root in resolved_roots):
        return
    raise RuntimeError("清理路径不在允许的 worktree 根目录下")


def _current_branch(target_repo: Path) -> str:
    rc, out, _ = _git_rc(target_repo, ["branch", "--show-current"])
    current = out.strip()
    return current if rc == 0 and current else "main"


def _apply_branch(
    config: Config,
    target_repo: Path,
    worktree_path: Path,
    branch: str,
    base_branch: str,
    target_app_path: str,
) -> dict[str, Any]:
    if _branch_has_commits(target_repo, branch, base_branch):
        commit = _git(target_repo, ["rev-parse", branch]).strip()
        rc, _, err = _git_rc(worktree_path, ["cherry-pick", "-n", commit])
        if rc != 0:
            raise RuntimeError(f"cherry-pick 冲突: {err}")
        return {
            "source_commit": commit,
            "apply_method": "cherry-pick-no-commit",
            "changed_files": _commit_changed_files(target_repo, commit, target_app_path),
        }

    fix_wt = branch_worktree_path(target_repo, branch) or worktree_path_for_branch(config.worktree_root, branch)
    if not fix_wt.exists():
        raise RuntimeError(f"找不到分支 {branch} 对应的 worktree")

    rc, diff_output, _ = _git_rc(fix_wt, ["diff", "--binary", "--", target_app_path], strip=False)
    if rc != 0 or not diff_output.strip():
        raise RuntimeError(f"分支 {branch} 没有可应用的改动")

    result = subprocess.run(
        ["git", "apply", "--3way"],
        input=diff_output,
        text=True,
        cwd=worktree_path,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git apply 失败: {result.stderr}")

    return {
        "source_commit": "",
        "apply_method": "diff-apply-3way",
        "changed_files": _worktree_changed_files(fix_wt, target_app_path),
    }


def _apply_preview_to_target(target_repo: Path, worktree_path: Path, target_app_path: str) -> None:
    rc, diff_output, _ = _git_rc(worktree_path, ["diff", "--binary", "HEAD", "--", target_app_path], strip=False)
    if rc != 0 or not diff_output.strip():
        raise RuntimeError("预演中没有可应用到目标分支的改动")
    result = subprocess.run(
        ["git", "apply", "--3way"],
        input=diff_output,
        text=True,
        cwd=target_repo,
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"应用到目标分支失败: {result.stderr}")


def _commit_message(data: dict[str, Any], target_app_path: str) -> str:
    scope = target_app_path.rstrip("/").split("/")[-1] or "app"
    lines = [f"fix({scope}): apply {data['branch']} validation", ""]
    lines.append(f"Source branch: {data['branch']}")
    if data.get("source_commit"):
        lines.append(f"Source commit: {data['source_commit']}")
    lines.append(f"Validation: {data['run_id']}")
    lines.append(f"Verified: {data.get('verify', {}).get('status', 'unknown')}")
    return "\n".join(lines)


def _record_commit_op(config: Config, branch: str, commit_sha: str, location: str, data: dict[str, Any]) -> None:
    """将提交操作写入 operations 数据库，失败不影响主流程。"""
    try:
        state = task_state(config, branch)
        issue_id = str(data.get("issue_id") or state.get("issue_id") or _issue_id_from_branch(branch))
        excel_row = _optional_int(state.get("excel_row"))
        source_operation_id = str(state.get("operation_id") or "")
        create_operation(
            config.storage_db_path,
            kind="fix-commit",
            workspace_id=config.active_workspace or "",
            status="committed",
            branch=branch,
            issue_id=issue_id,
            excel_row=excel_row,
            summary=json.dumps(
                {
                    "title": "已提交此修复",
                    "commit_sha": commit_sha,
                    "location": location,
                    "target_branch": data.get("target_branch", ""),
                    "run_id": data.get("run_id", ""),
                    "integration_branch": data.get("integration_branch", ""),
                    "changed_files": data.get("changed_files", []),
                    "source_operation_id": source_operation_id,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        )
    except Exception:
        pass  # 入库失败不阻断主流程


def _record_validation_op(config: Config, kind: str, status: str, branch: str, data: dict[str, Any]) -> None:
    try:
        create_operation(
            config.storage_db_path,
            kind=kind,
            workspace_id=config.active_workspace or "",
            status=status,
            branch=branch,
            issue_id=str(data.get("issue_id") or _issue_id_from_branch(branch)),
            summary=json.dumps(
                {
                    "title": _validation_op_title(kind, status),
                    "status": data.get("status", status),
                    "changed_files": data.get("changed_files", []),
                    "target_branch": data.get("target_branch", ""),
                    "integration_branch": data.get("integration_branch", ""),
                    "integration_worktree": data.get("integration_worktree", ""),
                    "final_commit": data.get("final_commit", ""),
                    "final_commit_location": data.get("final_commit_location", ""),
                    "revert_commit": data.get("revert_commit", ""),
                    "error": data.get("error", ""),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        )
    except Exception:
        pass


def _validation_op_title(kind: str, status: str) -> str:
    titles = {
        "fix-preview": "已生成提交预演" if status != "conflict" else "提交预演发生冲突",
        "fix-revert": "已撤回提交",
        "fix-undo-commit": "已撤销上次提交",
        "fix-remove-preview": "已移除提交预演",
        "fix-cleanup-source": "已清理来源分支",
    }
    return titles.get(kind, kind)


def _issue_id_from_branch(branch: str) -> str:
    match = re.match(r"^fix/(?:bug-)?(\d+)(?:-|$)", branch)
    return match.group(1) if match else ""


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _remove_preview_artifacts(config: Config, target_repo: Path, worktree_path: Path, integration_branch: str) -> None:
    _ensure_child_path(worktree_path, (_worktree_root(config),))
    if _is_registered_worktree(target_repo, worktree_path):
        _run_git_quiet(target_repo, ["worktree", "remove", "--force", str(worktree_path)])
        if _is_registered_worktree(target_repo, worktree_path):
            _run_git_quiet(target_repo, ["worktree", "prune"])
    if integration_branch.startswith("integration/"):
        _run_git_quiet(target_repo, ["branch", "-D", integration_branch])
    if worktree_path.exists():
        shutil.rmtree(worktree_path, ignore_errors=True)


def _is_registered_worktree(target_repo: Path, worktree_path: Path) -> bool:
    rc, out, _ = _git_rc(target_repo, ["worktree", "list", "--porcelain"])
    if rc != 0:
        return False
    expected = worktree_path.resolve()
    for line in out.splitlines():
        if line.startswith("worktree ") and Path(line.removeprefix("worktree ")).resolve() == expected:
            return True
    return False


def _branch_has_commits(target_repo: Path, branch: str, base_branch: str) -> bool:
    rc, out, _ = _git_rc(target_repo, ["log", f"{base_branch}..{branch}", "--oneline"])
    return rc == 0 and bool(out.strip())


def _commit_changed_files(target_repo: Path, commit: str, target_app_path: str) -> list[str]:
    rc, out, _ = _git_rc(target_repo, ["diff-tree", "--no-commit-id", "--name-only", "-r", commit, "--", target_app_path])
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


def _has_staged_changes(cwd: Path, target_app_path: str) -> bool:
    rc, out, _ = _git_rc(cwd, ["diff", "--cached", "--name-only", "--", target_app_path])
    return rc == 0 and bool(out.strip())


def _has_uncommitted_changes(cwd: Path) -> bool:
    rc, out, _ = _git_rc(cwd, ["status", "--porcelain"])
    return rc == 0 and bool(out.strip())
