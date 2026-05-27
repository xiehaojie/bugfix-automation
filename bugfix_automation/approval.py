from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any

from bugfix_automation.capability_system import install_capabilities, render_capability_contract
from bugfix_automation.config import Config
from bugfix_automation.excel_writer import update_cell_by_header
from bugfix_automation.runner import list_bugs
from bugfix_automation.runner import assert_scope_clean, codex_command, codex_log_path, runtime_path_prefix
from bugfix_automation.storage.repositories import create_ai_session, create_operation, finish_ai_session, finish_operation, index_ai_log_segments, new_id
from bugfix_automation.task_state import is_task_active, set_task_state, task_state
from bugfix_automation.worktree import changed_paths, commit_all, create_no_push_git_wrapper, symlink_node_modules, tracked_changed_files, write_worktree_exclude


@dataclass(frozen=True)
class FixWorktree:
    path: Path
    branch: str


def parse_worktree_list(output: str) -> list[FixWorktree]:
    fixes: list[FixWorktree] = []
    current_path: Path | None = None
    for line in output.splitlines():
        if line.startswith("worktree "):
            current_path = Path(line.removeprefix("worktree "))
        elif line.startswith("branch refs/heads/") and current_path is not None:
            branch = line.removeprefix("branch refs/heads/")
            if branch.startswith("fix/"):
                fixes.append(FixWorktree(path=current_path, branch=branch))
    return fixes


def load_fix_items(config: Config) -> list[dict[str, Any]]:
    output = _git(config.target_repo, ["worktree", "list", "--porcelain"])
    items: list[dict[str, Any]] = []
    for fix in parse_worktree_list(output):
        changed_files = tracked_changed_files(fix.path, config.target_app_path)
        app_diff = _git(fix.path, ["diff", "HEAD", "--", config.target_app_path])
        # For files in changed_files but missing from diff, generate synthetic diff
        diff_paths: set[str] = set()
        for line in app_diff.splitlines():
            m = re.match(r"^diff --git a/(.+?) b/", line)
            if m:
                diff_paths.add(m.group(1))
        for cf in changed_files:
            if cf not in diff_paths:
                file_path = fix.path / cf
                if file_path.exists():
                    try:
                        content = file_path.read_text(errors="replace")
                        lines = content.splitlines()
                        app_diff += f"\ndiff --git a/{cf} b/{cf}\nnew file mode 100644\n--- /dev/null\n+++ b/{cf}\n@@ -0,0 +1,{len(lines)} @@\n"
                        app_diff += "\n".join(f"+{line}" for line in lines)
                    except Exception:
                        pass
                else:
                    # File was deleted – show empty deletion marker
                    app_diff += f"\ndiff --git a/{cf} b/{cf}\ndeleted file mode 100644\n--- a/{cf}\n+++ /dev/null\n"
        status = _git(fix.path, ["status", "--short", "--", config.target_app_path])
        state = task_state(config, fix.branch)
        active = is_task_active(config, fix.branch)
        items.append(
            {
                "branch": fix.branch,
                "path": str(fix.path),
                "changed_files": changed_files,
                "pending": bool(changed_files),
                "active": active,
                "task_status": state.get("status", ""),
                "task_phase": state.get("phase", ""),
                "task_detail": state.get("detail", ""),
                "task_updated_at": state.get("updated_at", ""),
                "excel_row": state.get("excel_row", 0),
                "issue_id": state.get("issue_id", ""),
                "description": state.get("description", ""),
                "status": status,
                "diff": app_diff,
                "log_path": str(codex_log_path(config, fix.branch)),
            }
        )
    return items


def count_pending(items: list[dict[str, Any]]) -> int:
    return sum(1 for item in items if bool(item.get("active")) or bool(item.get("pending")) or bool(item.get("changed_files")))


def approve_fix(config: Config, branch: str) -> str:
    if is_task_active(config, branch):
        state = task_state(config, branch)
        raise RuntimeError(f"任务仍在执行中，不能审批提交：{state.get('status', '')}/{state.get('phase', '')}")
    fix = _find_fix(config, branch)
    changed_files = tracked_changed_files(fix.path, config.target_app_path)
    if not changed_files:
        raise RuntimeError("没有可审批的 pc-web 改动")
    diff_preview = _diff_preview(fix.path, config.target_app_path)
    scope = config.target_app_path.rstrip("/").split("/")[-1] or "frontend"
    message = f"fix({scope}): {branch.removeprefix('fix/')}"
    commit = commit_all(fix.path, message, config.target_app_path)
    mark_excel_processed(config, branch)
    _record_branch_operation(
        config,
        kind="fix-approve",
        status="committed",
        branch=branch,
        summary={
            "title": "已审批并提交修复",
            "commit": commit,
            "changed_files": changed_files,
            "diff_preview": diff_preview,
            "log_path": str(codex_log_path(config, branch)),
        },
    )
    remove_worktree(config, branch)
    return commit


def reject_fix(config: Config, branch: str) -> None:
    if is_task_active(config, branch):
        state = task_state(config, branch)
        raise RuntimeError(f"任务仍在执行中，不能拒绝删除：{state.get('status', '')}/{state.get('phase', '')}")
    from bugfix_automation.application.fix_validation_service import discard_preview_for_source_branch

    changed_files: list[str] = []
    diff_preview = ""
    try:
        fix = _find_fix(config, branch)
        changed_files = tracked_changed_files(fix.path, config.target_app_path)
        diff_preview = _diff_preview(fix.path, config.target_app_path)
    except RuntimeError:
        fix = None
    discard_preview_for_source_branch(config, branch)
    # 尝试移除 worktree（可能已经不存在）
    try:
        if fix is None:
            fix = _find_fix(config, branch)
        subprocess.run(["git", "worktree", "remove", "--force", str(fix.path)], cwd=config.target_repo, capture_output=True)
    except RuntimeError:
        pass  # worktree 可能已被移除
    # 删除本地分支
    subprocess.run(["git", "branch", "-D", branch], cwd=config.target_repo, capture_output=True)
    _record_branch_operation(
        config,
        kind="fix-reject",
        status="rejected",
        branch=branch,
        summary={
            "title": "已拒绝并删除修复",
            "changed_files": changed_files,
            "diff_preview": diff_preview,
            "log_path": str(codex_log_path(config, branch)),
        },
    )


def remove_worktree(config: Config, branch: str) -> None:
    fix = _find_fix(config, branch)
    subprocess.run(["git", "worktree", "remove", "--force", str(fix.path)], cwd=config.target_repo, check=True)


def mark_excel_processed(config: Config, branch: str) -> bool:
    state = task_state(config, branch)
    if state.get("excel_row"):
        update_cell_by_header(
            config.excel_path,
            config.sheet_name,
            int(state["excel_row"]),
            config.excel_processed_status_column,
            config.excel_processed_status_value,
        )
        return True
    branch_issue_id = _branch_issue_id(branch)
    for bug in list_bugs(config):
        if branch_issue_id and bug.issue_id == branch_issue_id:
            update_cell_by_header(
                config.excel_path,
                config.sheet_name,
                bug.excel_row,
                config.excel_processed_status_column,
                config.excel_processed_status_value,
            )
            return True
    return False


def _branch_issue_id(branch: str) -> str:
    if branch.startswith("fix/bug-"):
        without_prefix = branch.removeprefix("fix/bug-")
        prefix, separator, stamp = without_prefix.rpartition("-")
        if separator and re.fullmatch(r"\d{12}", stamp):
            return prefix.split("-", 1)[0]
    if branch.startswith("fix/"):
        return branch.removeprefix("fix/").split("-", 1)[0]
    return ""


def rework_fix(config: Config, branch: str, note: str = "", file_paths: list[str] | None = None, image_paths: list[str] | None = None) -> None:
    if is_task_active(config, branch):
        state = task_state(config, branch)
        raise RuntimeError(f"任务仍在执行中，不能重新修改：{state.get('status', '')}/{state.get('phase', '')}")
    fix = _find_fix(config, branch)
    normalized_images = [Path(path).expanduser() for path in image_paths or [] if path.strip()]
    write_worktree_exclude(fix.path)
    symlink_node_modules(fix.path, config.target_repo)
    install_capabilities(config, fix.path, Path(__file__).resolve().parents[1])
    prompt = _rework_prompt(config, branch, note, file_paths or [], normalized_images)
    git_wrapper_dir = create_no_push_git_wrapper(fix.path)
    path_prefix = runtime_path_prefix(config.target_repo, git_wrapper_dir)
    operation_id = _create_branch_operation(
        config,
        kind="fix-rework",
        status="running",
        branch=branch,
        summary={
            "title": "正在根据补充对话重新修改",
            "note": note,
            "file_paths": file_paths or [],
            "image_paths": [str(path) for path in normalized_images],
            "log_path": str(codex_log_path(config, branch)),
        },
    )
    ai_session_id, ai_log_path = _start_rework_ai_session(config, operation_id, branch, fix.path, prompt)
    set_task_state(config, branch, "reworking", detail="正在根据补充信息重新修改。", phase="codex", image_paths=normalized_images, operation_id=operation_id)
    try:
        _run(codex_command(config.cli_tool, str(fix.path), prompt, normalized_images), cwd=fix.path, path_prefix=path_prefix, stdin_text=prompt, log_path=codex_log_path(config, branch))
        assert_scope_clean(changed_paths(fix.path), config.target_app_path)
        _git(fix.path, ["diff", "--check", "--", config.target_app_path])
        changed_files = tracked_changed_files(fix.path, config.target_app_path)
        _finish_rework_ai_session(config, ai_session_id, ai_log_path, codex_log_path(config, branch), "succeeded", branch, changed_files)
        finish_operation(
            config.storage_db_path,
            operation_id=operation_id,
            status="succeeded",
            summary=_summary_json({
                "title": "重新修改完成，等待审批",
                "note": note,
                "file_paths": file_paths or [],
                "image_paths": [str(path) for path in normalized_images],
                "changed_files": changed_files,
                "diff_preview": _diff_preview(fix.path, config.target_app_path),
                "log_path": str(codex_log_path(config, branch)),
            }),
        )
        set_task_state(config, branch, "pending-approval", detail="重新修改完成，等待审批。", phase="done", image_paths=normalized_images, operation_id=operation_id)
    except Exception as exc:
        _finish_rework_ai_session(config, ai_session_id, ai_log_path, codex_log_path(config, branch), "failed", branch, [])
        finish_operation(
            config.storage_db_path,
            operation_id=operation_id,
            status="failed",
            summary=_summary_json({"title": "重新修改失败", "error": f"{type(exc).__name__}: {exc}", "note": note, "log_path": str(codex_log_path(config, branch))}),
        )
        set_task_state(config, branch, "failed", detail=f"{type(exc).__name__}: {exc}", phase="failed", image_paths=normalized_images, operation_id=operation_id)
        raise


def _find_fix(config: Config, branch: str) -> FixWorktree:
    for fix in parse_worktree_list(_git(config.target_repo, ["worktree", "list", "--porcelain"])):
        if fix.branch == branch:
            return fix
    raise RuntimeError(f"没有找到修复分支: {branch}")


def _git(cwd: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=True,
    )
    return result.stdout


def _create_branch_operation(config: Config, *, kind: str, status: str, branch: str, summary: dict[str, Any]) -> str:
    state = task_state(config, branch)
    return create_operation(
        config.storage_db_path,
        kind=kind,
        workspace_id=config.active_workspace,
        status=status,
        branch=branch,
        issue_id=str(state.get("issue_id") or _branch_issue_id(branch)),
        excel_row=int(state["excel_row"]) if state.get("excel_row") else None,
        summary=_summary_json(summary),
    )


def _record_branch_operation(config: Config, *, kind: str, status: str, branch: str, summary: dict[str, Any]) -> None:
    try:
        _create_branch_operation(config, kind=kind, status=status, branch=branch, summary=summary)
    except Exception:
        pass


def _summary_json(summary: dict[str, Any]) -> str:
    return json.dumps(summary, ensure_ascii=False, sort_keys=True)


def _diff_preview(worktree_path: Path, target_app_path: str) -> str:
    try:
        return _git(worktree_path, ["diff", "--", target_app_path])[:80000]
    except Exception:
        return ""


def _start_rework_ai_session(config: Config, operation_id: str, branch: str, worktree_path: Path, prompt: str) -> tuple[str, Path]:
    ai_session_id = new_id("ai")
    ai_dir = config.logs_root / "ai" / ai_session_id
    prompt_path = ai_dir / "prompt.txt"
    ai_log_path = ai_dir / "full.log"
    ai_dir.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(prompt, encoding="utf-8")
    create_ai_session(
        config.storage_db_path,
        operation_id=operation_id,
        provider="local-cli",
        cli_tool=config.cli_tool,
        workspace_path=worktree_path,
        prompt_path=prompt_path,
        log_path=ai_log_path,
        ai_session_id=ai_session_id,
    )
    return ai_session_id, ai_log_path


def _finish_rework_ai_session(config: Config, ai_session_id: str, ai_log_path: Path, branch_log_path: Path, status: str, branch: str, changed_files: list[str]) -> None:
    try:
        if branch_log_path.exists():
            ai_log_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(branch_log_path, ai_log_path)
        index_ai_log_segments(config.storage_db_path, ai_session_id=ai_session_id, log_path=ai_log_path)
        finish_ai_session(
            config.storage_db_path,
            ai_session_id=ai_session_id,
            status=status,
            log_path=ai_log_path,
            summary={"branch": branch, "changed_files": changed_files},
        )
    except Exception:
        pass


def _run(command: list[str], cwd: Path, path_prefix: str | Path | None = None, stdin_text: str | None = None, log_path: Path | None = None) -> None:
    import os

    env = os.environ.copy()
    if path_prefix is not None:
        env["PATH"] = f"{path_prefix}{os.pathsep}{env.get('PATH', '')}"
    text_kwargs = {"text": True, "encoding": "utf-8", "errors": "replace"} if stdin_text is not None else {}
    timeout_seconds = int(env.get("BUGFIX_AI_CLI_TIMEOUT_SECONDS", "1800"))
    if log_path is None:
        subprocess.run(command, cwd=cwd, env=env, input=stdin_text, check=True, timeout=timeout_seconds, **text_kwargs)
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(f"\n$ {' '.join(command)}\n")
        log_file.flush()
        subprocess.run(command, cwd=cwd, env=env, input=stdin_text, stdout=log_file, stderr=subprocess.STDOUT, check=True, timeout=timeout_seconds, **text_kwargs)


def _rework_prompt(config: Config, branch: str, note: str, file_paths: list[str], image_paths: list[Path]) -> str:
    from bugfix_automation.prompt import PROMPTS_DIR

    files = "\n".join(f"- {path}" for path in file_paths if path.strip()) or "- 无"
    images = "\n".join(f"- {path}" for path in image_paths) or "- 无"
    template = (PROMPTS_DIR / "rework.md").read_text(encoding="utf-8").strip()
    return template.format(
        branch=branch,
        target_app_path=config.target_app_path,
        note=note or "无",
        file_paths=files,
        image_paths=images,
        capability_contract=render_capability_contract(config),
    )
