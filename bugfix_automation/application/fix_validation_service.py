from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from bugfix_automation.config import Config, active_workspace_config
from bugfix_automation.worktree import branch_worktree_path, worktree_path_for_branch

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


def get_verify_log(config: Config, branch: str) -> str:
    """读取 AI 验证日志全文，供前端展示。"""
    _validate_fix_branch(config, branch)
    log_file = _validation_dir(config, branch) / "ai-verify.log"
    if not log_file.exists():
        return ""
    return log_file.read_text(encoding="utf-8")


def verify(config: Config, branch: str, *, commands_override: list[list[str]] | None = None) -> dict[str, Any]:
    """验证流程分两段锁：

    阶段 1（有锁）：状态校验 + git worktree 创建 + cherry-pick。
    阶段 2（无锁）：AI CLI 验证，可能耗时 10 分钟，期间不阻塞提交等其他操作。
    阶段 3（有锁）：写回验证结果并更新状态。
    """
    _validate_fix_branch(config, branch)

    # ── 阶段 1：建立 worktree、应用改动 ──────────────────────────────
    with _validation_lock(config, branch):
        data = get_validation(config, branch)
        if data["status"] in {"committed", "cleaned"}:
            raise RuntimeError(f"验证单状态为 {data['status']}，不能重新验证")

        data["status"] = "verifying"
        data["error"] = ""
        data["verify"] = {"status": "", "commands": []}
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

        target_app_path = workspace.target_app_path if workspace else config.target_app_path
        try:
            applied = _apply_branch(config, target_repo, worktree_path, branch, target_branch, target_app_path)
        except RuntimeError as exc:
            _run_git_quiet(worktree_path, ["cherry-pick", "--abort"])
            data["status"] = "conflict"
            data["error"] = str(exc)
            _save_validation(config, branch, data)
            return data

        data.update(applied)
        data["changed_files"] = applied["changed_files"]
        _save_validation(config, branch, data)
        # 锁在此处释放，后续 AI 验证不会阻塞提交等操作

    # ── 阶段 2：AI 验证（无锁，可能耗时较长）────────────────────────
    verify_result = _run_verify(config, branch, worktree_path, commands_override=commands_override)

    # ── 阶段 3：写回结果（重新加锁）────────────────────────────────
    with _validation_lock(config, branch):
        data = get_validation(config, branch)  # 重新读取，避免并发写入覆盖
        data["verify"] = verify_result
        data["status"] = "ready-to-commit" if verify_result["status"] in {"passed", "skipped"} else "verify-failed"
        _save_validation(config, branch, data)
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

        # 提交成功后自动清理：integration worktree/branch + fix worktree/branch
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
            if not cwd.exists():
                raise RuntimeError("提交所在 worktree 不存在，不能撤回")
            if _has_uncommitted_changes(cwd):
                raise RuntimeError("提交所在工作区不干净，不能撤回")
            _run_git(cwd, ["revert", "--no-edit", data["final_commit"]])
            data["revert_commit"] = _git(cwd, ["rev-parse", "HEAD"]).strip()

        data["status"] = "reverted"
        _save_validation(config, branch, data)
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
            if not cwd.exists():
                raise RuntimeError("提交所在仓库不存在")
            # 验证 HEAD 确实是我们的提交
            current_head = _git(cwd, ["rev-parse", "HEAD"]).strip()
            if current_head != data["final_commit"]:
                raise RuntimeError(
                    f"当前 HEAD ({current_head[:8]}) 不是此修复的提交 ({data['final_commit'][:8]})，"
                    "可能有新提交在其之上，不能安全撤销。请用「撤回此提交」(revert) 代替。"
                )
            _run_git(cwd, ["reset", "--soft", "HEAD~1"])

        data["status"] = "ready-to-commit"
        data.pop("final_commit", None)
        data.pop("final_commit_location", None)
        _save_validation(config, branch, data)
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
        return data


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

    rc, diff_output, _ = _git_rc(fix_wt, ["diff", "--binary", "--", target_app_path])
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


def _ensure_node_modules(target_repo: Path, worktree_path: Path) -> tuple[bool, str]:
    """为 worktree 准备 node_modules（仅前端项目需要）。

    返回 (是否成功, 日志)。失败不抛异常，由调用方决定如何继续。
    """
    if not (worktree_path / "package.json").exists():
        return True, ""  # 非 Node 项目，跳过

    # 优先尝试 pnpm install --prefer-offline（不带 frozen-lockfile，更宽松）
    for pm_cmd, label in (
        (["pnpm", "install", "--prefer-offline", "--ignore-scripts"], "pnpm"),
        (["npm", "install", "--prefer-offline", "--no-audit", "--no-fund", "--ignore-scripts"], "npm"),
    ):
        try:
            result = subprocess.run(
                pm_cmd, cwd=worktree_path, capture_output=True, text=True, timeout=300,
            )
            if result.returncode == 0:
                return True, f"[{label}] install ok\n"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    # 降级：从原 repo 软链根 node_modules（pc-web 子包用 .bin 软链兜底）
    src = target_repo / "node_modules"
    dst = worktree_path / "node_modules"
    if src.exists() and not dst.exists():
        try:
            dst.symlink_to(src)
            return True, "[fallback] symlink root node_modules\n"
        except OSError as exc:
            return False, f"[fallback] symlink failed: {exc}\n"
    return False, "[install] all attempts failed\n"


def _run_command_capture(cmd: list[str], cwd: Path, log_handle, timeout: int = 600) -> int:
    """执行命令并把输出同步写到 log_handle，返回 exit code。"""
    header = f"\n{'=' * 60}\n$ {' '.join(cmd)}\n  (cwd: {cwd})\n{'=' * 60}\n"
    log_handle.write(header)
    log_handle.flush()
    try:
        proc = subprocess.Popen(
            cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
    except FileNotFoundError as exc:
        log_handle.write(f"[ERROR] command not found: {exc}\n")
        log_handle.flush()
        return 127

    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            log_handle.write(line)
            log_handle.flush()
        return proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        log_handle.write(f"\n[TIMEOUT] killed after {timeout}s\n")
        log_handle.flush()
        return 124


def _run_verify(config: Config, branch: str, worktree_path: Path, *, commands_override: list[list[str]] | None = None) -> dict[str, Any]:
    """直接由 Python 执行验证命令，不再走 AI 沙箱。

    设计要点：
    - 沙箱外执行：拥有完整 PATH 与网络，避免 codex sandbox 的环境裁剪
    - 实时输出到 ai-verify.log，前端「验证 AI」tab 直接展示
    - 依据每条命令的 exit code 判定 pass/fail，无需 AI 解析
    - 命令列表由 workspace.verify_commands 配置，前后端任意命令都能跑
    - 支持 commands_override 由用户在 UI 临时指定
    """
    workspace = active_workspace_config(config)
    # commands_override=[] 表示用户显式跳过验证，commands_override=None 使用配置默认值
    verify_commands = commands_override if commands_override is not None else (workspace.verify_commands if workspace else None)
    if not verify_commands:
        return {"status": "skipped", "commands": []}

    target_app_path = (workspace.target_app_path if workspace else None) or config.target_app_path
    app_path = worktree_path / target_app_path
    target_repo = Path(config.target_repo)

    log_file = _validation_dir(config, branch) / "ai-verify.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    commands_result: list[dict[str, Any]] = []
    with log_file.open("w", encoding="utf-8") as log_handle:
        log_handle.write(f"=== Fix validation @ {datetime.now().isoformat()} ===\n")
        log_handle.write(f"Branch: {branch}\nWorktree: {worktree_path}\nApp: {app_path}\n")
        log_handle.flush()

        # 1) 准备依赖（仅前端项目；其他语言可在 verify_commands 里自己声明）
        ok, install_log = _ensure_node_modules(target_repo, worktree_path)
        log_handle.write("\n--- prepare dependencies ---\n" + install_log)
        log_handle.flush()

        # 2) 顺序执行验证命令，记录每条结果
        for cmd in verify_commands:
            cmd_str = " ".join(cmd)
            # 命令在 worktree 根目录执行（monorepo 工作流要求）
            exit_code = _run_command_capture(list(cmd), worktree_path, log_handle, timeout=600)
            status = "passed" if exit_code == 0 else "failed"
            log_handle.write(f"\n[RESULT] {cmd_str} => {status} (exit={exit_code})\n")
            log_handle.flush()

            tail = ""
            if status == "failed":
                # 重新读最后 40 行作为摘要（流式写入时无法直接取尾部）
                try:
                    log_handle.flush()
                    text = log_file.read_text(encoding="utf-8", errors="replace")
                    tail = _tail_log(text, 40)
                except OSError:
                    tail = f"exit code {exit_code}"

            commands_result.append({
                "command": cmd_str,
                "status": status,
                "log_path": str(log_file),
                "log_tail": tail,
            })

        overall = "passed" if all(c["status"] == "passed" for c in commands_result) else "failed"
        log_handle.write(f"\n=== OVERALL: {overall} ===\n")

    return {"status": overall, "commands": commands_result}


def _tail_log(text: str, lines: int = 40) -> str:
    """返回日志最后 N 行，用于前端内联展示错误摘要。"""
    return "\n".join(text.splitlines()[-lines:])


def _command_log_slug(cmd_list: list[str]) -> str:
    raw = "-".join(cmd_list)
    slug = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in raw).strip("-.") or "command"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:10]
    return f"{slug[:80].rstrip('-.')}-{digest}"


def _apply_preview_to_target(target_repo: Path, worktree_path: Path, target_app_path: str) -> None:
    rc, diff_output, _ = _git_rc(worktree_path, ["diff", "--binary", "HEAD", "--", target_app_path])
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


def _remove_preview_artifacts(config: Config, target_repo: Path, worktree_path: Path, integration_branch: str) -> None:
    _ensure_child_path(worktree_path, (_worktree_root(config),))
    if worktree_path.exists():
        _run_git_quiet(target_repo, ["worktree", "remove", "--force", str(worktree_path)])
    if integration_branch.startswith("integration/"):
        _run_git_quiet(target_repo, ["branch", "-D", integration_branch])
    if worktree_path.exists():
        shutil.rmtree(worktree_path)


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
    files: list[str] = []
    for line in out.splitlines():
        raw_path = line[3:]
        if " -> " in raw_path:
            raw_path = raw_path.split(" -> ", 1)[1]
        if raw_path:
            files.append(raw_path)
    return sorted(files)


def _has_staged_changes(cwd: Path, target_app_path: str) -> bool:
    rc, out, _ = _git_rc(cwd, ["diff", "--cached", "--name-only", "--", target_app_path])
    return rc == 0 and bool(out.strip())


def _has_uncommitted_changes(cwd: Path) -> bool:
    rc, out, _ = _git_rc(cwd, ["status", "--porcelain"])
    return rc == 0 and bool(out.strip())


def _git(cwd: Path, args: list[str]) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, check=True)
    return result.stdout


def _git_rc(cwd: Path, args: list[str]) -> tuple[int, str, str]:
    result = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True)
    return result.returncode, result.stdout, result.stderr


def _run_git(cwd: Path, args: list[str]) -> None:
    subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, check=True)


def _run_git_quiet(cwd: Path, args: list[str]) -> None:
    subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True)
