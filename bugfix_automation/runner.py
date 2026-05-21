from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import shutil
import subprocess
from pathlib import Path
from typing import Any
import os
import threading

from bugfix_automation.codex_summary import branch_name_from_summary, generate_codex_change_summary
from bugfix_automation.config import Config, active_workspace_config
from bugfix_automation.excel_reader import read_sheet
from bugfix_automation.filtering import BugRecord, filter_bugs, make_branch_name
from bugfix_automation.images import export_bug_images
from bugfix_automation.prompt import render_codex_prompt
from bugfix_automation.reporter import write_reports
from bugfix_automation.storage.repositories import (
    create_ai_session,
    create_operation,
    finish_ai_session,
    finish_operation,
    index_ai_log_segments,
    new_id,
    save_config_snapshot,
)
from bugfix_automation.task_state import is_task_active, rename_task_state, set_task_state
from bugfix_automation.worktree import (
    changed_paths,
    create_no_push_git_wrapper,
    ensure_worktree,
    has_app_changes,
    install_project_agents,
    out_of_scope_paths,
    rename_current_branch,
    branch_exists,
    branch_worktree_path,
    worktree_path_for_branch,
    symlink_node_modules,
    tracked_changed_files,
    write_worktree_exclude,
)

WORKTREE_LOCK = threading.Lock()


def list_bugs(config: Config) -> list[BugRecord]:
    rows = read_sheet(config.excel_path, config.sheet_name)
    return filter_bugs(rows, config.assignee, {config.excel_processed_status_value}, config.filters)


def run_once(config: Config, dry_run: bool = False) -> tuple[Path, Path, Path]:
    bugs = list_bugs(config)
    run_dir = config.runs_root / date.today().isoformat()
    run_stamp = datetime.now().strftime("%Y%m%d%H%M")
    operation_id = _create_run_operation(config, "run_once", status="running", summary=f"{len(bugs)} bugs matched")
    if dry_run:
        results = []
        for bug in bugs:
            branch = make_branch_name(bug, config.branch_summary_fields, run_stamp)
            image_paths = export_bug_images(config.excel_path, bug, run_dir / "images" / branch.replace("/", "-"))
            results.append(_result(bug, "dry-run", branch, "命中筛选规则；演练模式未创建 worktree，也未启动 Codex。", image_paths))
        paths = write_reports(run_dir, results)
        finish_operation(config.storage_db_path, operation_id=operation_id, status="succeeded", summary=f"dry-run: {len(results)} bugs")
        return paths

    results: list[dict[str, Any]] = []
    max_workers = max(1, min(config.max_concurrency, len(bugs) or 1))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_bug = {}
        for bug in bugs:
            branch = make_branch_name(bug, config.branch_summary_fields, run_stamp)
            image_paths = export_bug_images(config.excel_path, bug, run_dir / "images" / branch.replace("/", "-"))
            if is_task_active(config, branch):
                results.append(_result(bug, "skipped", branch, "已有任务正在执行，跳过本次重复启动。", image_paths, log_path=codex_log_path(config, branch)))
                continue
            set_task_state(config, branch, "queued", bug, detail="等待并发队列调度。", phase="queued", image_paths=image_paths, operation_id=operation_id)
            future = executor.submit(process_bug, config, bug, branch, image_paths, codex_log_path(config, branch), operation_id)
            future_to_bug[future] = bug
        for future in as_completed(future_to_bug):
            results.append(future.result())
    results.sort(key=lambda item: int(item.get("excel_row", 0) or 0))
    paths = write_reports(run_dir, results)
    failed = any(result.get("status") == "failed" for result in results)
    finish_operation(
        config.storage_db_path,
        operation_id=operation_id,
        status="failed" if failed else "succeeded",
        summary=f"{len(results)} results",
    )
    return paths


def run_one(config: Config, issue_id: str | None = None, excel_row: int | None = None, dry_run: bool = False) -> tuple[Path, Path, Path]:
    bug = select_one_bug(list_bugs(config), issue_id=issue_id, excel_row=excel_row)
    run_dir = config.runs_root / date.today().isoformat() / f"single-row-{bug.excel_row}"
    branch = make_branch_name(bug, config.branch_summary_fields, datetime.now().strftime("%Y%m%d%H%M"))
    image_paths = export_bug_images(config.excel_path, bug, run_dir / "images" / branch.replace("/", "-"))
    operation_id = _create_run_operation(
        config,
        "run_one",
        status="running",
        branch=branch,
        issue_id=bug.issue_id,
        excel_row=bug.excel_row,
        summary=f"Excel row {bug.excel_row}",
    )
    if dry_run:
        result = _result(bug, "dry-run", branch, "命中筛选规则；单条演练模式只导出截图和报告。", image_paths)
    else:
        result = process_bug(config, bug, branch, image_paths, codex_log_path(config, branch), operation_id)
    paths = write_bug_results(run_dir, [result])
    finish_operation(
        config.storage_db_path,
        operation_id=operation_id,
        status="failed" if result.get("status") == "failed" else "succeeded",
        summary=str(result.get("detail", "")),
    )
    return paths


def select_one_bug(bugs: list[BugRecord], issue_id: str | None, excel_row: int | None) -> BugRecord:
    if not issue_id and excel_row is None:
        raise ValueError("请提供 issue_id 或 excel_row")
    matches = [
        bug
        for bug in bugs
        if (issue_id is not None and bug.issue_id == issue_id)
        or (excel_row is not None and bug.excel_row == excel_row)
    ]
    if not matches:
        raise ValueError("在筛选后的 bug 列表中没有找到匹配项")
    if len(matches) > 1:
        raise ValueError("找到多条匹配 bug；请使用 --row 指定精确的 Excel 行号")
    return matches[0]


def write_bug_results(run_dir: Path, results: list[dict[str, Any]]) -> tuple[Path, Path, Path]:
    return write_reports(run_dir, results)


def process_bug(
    config: Config,
    bug: BugRecord,
    branch: str,
    image_paths: list[Path],
    log_path: Path | None = None,
    operation_id: str | None = None,
) -> dict[str, Any]:
    worktree_path: Path | None = None
    try:
        set_task_state(config, branch, "running", bug, detail="开始准备 worktree。", phase="prepare", image_paths=image_paths, operation_id=operation_id)
        existing_path = worktree_path_for_branch(config.worktree_root, branch)
        if existing_path.exists():
            result = _result(bug, "skipped", branch, f"worktree 已存在：{existing_path}", image_paths, log_path=log_path)
            set_task_state(config, branch, result["status"], bug, detail=result["detail"], phase="done", image_paths=image_paths, operation_id=operation_id)
            return result
        existing_branch_path = branch_worktree_path(config.target_repo, branch)
        if existing_branch_path is not None:
            result = _result(bug, "skipped", branch, f"分支已经在这个 worktree 中检出：{existing_branch_path}", image_paths, log_path=log_path)
            set_task_state(config, branch, result["status"], bug, detail=result["detail"], phase="done", image_paths=image_paths, operation_id=operation_id)
            return result
        if branch_exists(config.target_repo, branch):
            result = _result(bug, "skipped", branch, "目标仓库中已存在同名分支。", image_paths, log_path=log_path)
            set_task_state(config, branch, result["status"], bug, detail=result["detail"], phase="done", image_paths=image_paths, operation_id=operation_id)
            return result
        with WORKTREE_LOCK:
            worktree_path = ensure_worktree(config.target_repo, config.worktree_root, branch)
        write_worktree_exclude(worktree_path)
        symlink_node_modules(worktree_path, config.target_repo)
        install_project_agents(worktree_path, Path(__file__).resolve().parents[1])
        git_wrapper_dir = create_no_push_git_wrapper(worktree_path)
        workspace = active_workspace_config(config)
        prompt = render_codex_prompt(
            bug,
            config.target_app_path,
            prompt_fields=config.prompt_fields,
            prompt_template=config.prompt_template,
            context_paths=config.prompt_context_paths,
            workspace_name=workspace.name,
            image_paths=image_paths,
            scope=workspace.scope,
        )
        set_task_state(config, branch, "running", bug, detail="AI 正在分析并尝试修复。", phase="codex", image_paths=image_paths, operation_id=operation_id)
        ai_session = _start_ai_session(config, operation_id, config.cli_tool, worktree_path, prompt, log_path)
        try:
            _run(ai_cli_command(config.cli_tool, str(worktree_path), prompt, image_paths), cwd=worktree_path, path_prefix=git_wrapper_dir, stdin_text=prompt, log_path=log_path)
        except Exception:
            _finish_ai_session(config, ai_session, log_path, branch, bug, status="failed")
            raise
        else:
            _finish_ai_session(config, ai_session, log_path, branch, bug, status="succeeded")
        assert_scope_clean(changed_paths(worktree_path), config.target_app_path)
        set_task_state(config, branch, "verifying", bug, detail="Codex 已结束，正在运行验证命令。", phase="verify", image_paths=image_paths, operation_id=operation_id)
        _verify_frontend(worktree_path, config, log_path)
        assert_scope_clean(changed_paths(worktree_path), config.target_app_path)
        if not has_app_changes(worktree_path, config.target_app_path):
            result = _result(bug, "no-change", branch, "Codex 已结束，但没有产生本地改动。", image_paths, log_path=log_path)
            set_task_state(config, branch, result["status"], bug, detail=result["detail"], phase="done", image_paths=image_paths, operation_id=operation_id)
            return result
        changed_files = tracked_changed_files(worktree_path, config.target_app_path)
        branch, log_path = _rename_branch_from_codex_summary(config, worktree_path, bug, branch, log_path)
        result = _result(
            bug,
            "pending-approval",
            branch,
            f"已生成待审批改动：{worktree_path}。",
            image_paths,
            changed_files=changed_files,
            log_path=log_path,
        )
        set_task_state(config, branch, result["status"], bug, detail=result["detail"], phase="done", image_paths=image_paths, operation_id=operation_id)
        return result
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"
        if worktree_path is not None:
            detail = f"{detail}; worktree={worktree_path}"
        result = _result(bug, "failed", branch, detail, image_paths, log_path=log_path)
        set_task_state(config, branch, result["status"], bug, detail=detail, phase="failed", image_paths=image_paths, operation_id=operation_id)
        return result


def _create_run_operation(
    config: Config,
    kind: str,
    *,
    status: str,
    branch: str = "",
    issue_id: str = "",
    excel_row: int | None = None,
    summary: str = "",
) -> str:
    snapshot_id = save_config_snapshot(config.storage_db_path, kind, _config_snapshot(config))
    return create_operation(
        config.storage_db_path,
        kind=kind,
        workspace_id=config.active_workspace,
        status=status,
        branch=branch,
        issue_id=issue_id,
        excel_row=excel_row,
        config_snapshot_id=snapshot_id,
        summary=summary,
    )


def _config_snapshot(config: Config) -> dict[str, Any]:
    return _json_safe(asdict(config))


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return value


def _start_ai_session(
    config: Config,
    operation_id: str | None,
    cli_tool: str,
    worktree_path: Path,
    prompt: str,
    branch_log_path: Path | None,
) -> dict[str, Any] | None:
    if not operation_id:
        return None
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
        cli_tool=cli_tool,
        workspace_path=worktree_path,
        prompt_path=prompt_path,
        log_path=ai_log_path,
        ai_session_id=ai_session_id,
    )
    return {"id": ai_session_id, "log_path": ai_log_path, "branch_log_path": branch_log_path}


def _finish_ai_session(
    config: Config,
    ai_session: dict[str, Any] | None,
    branch_log_path: Path | None,
    branch: str,
    bug: BugRecord,
    status: str,
) -> None:
    if not ai_session:
        return
    ai_log_path = Path(ai_session["log_path"])
    if branch_log_path is not None and branch_log_path.exists():
        ai_log_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(branch_log_path, ai_log_path)
    index_ai_log_segments(config.storage_db_path, ai_session_id=str(ai_session["id"]), log_path=ai_log_path)
    finish_ai_session(
        config.storage_db_path,
        ai_session_id=str(ai_session["id"]),
        status=status,
        log_path=ai_log_path,
        summary={"branch": branch, "issue_id": bug.issue_id, "excel_row": bug.excel_row},
    )


def ai_cli_command(cli_tool: str, worktree_path: str, prompt: str, image_paths: list[Path] | None = None) -> list[str]:
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


# Backward-compatible alias
codex_command = ai_cli_command


def assert_scope_clean(paths: list[str], target_app_path: str) -> None:
    unsafe_paths = out_of_scope_paths(paths, target_app_path)
    if unsafe_paths:
        raise RuntimeError(f"检测到超出前端范围的改动：{', '.join(unsafe_paths)}")


def _verify_frontend(worktree_path: Path, config: Config, log_path: Path | None = None) -> None:
    workspace = active_workspace_config(config)
    if not workspace.verify_commands:
        # No verify commands configured: trust the AI to self-verify per its prompt.
        return
    app_path = worktree_path / config.target_app_path
    for command in workspace.verify_commands:
        _run(list(command), cwd=app_path, log_path=log_path)


def _run(command: list[str], cwd: Path, path_prefix: Path | None = None, stdin_text: str | None = None, log_path: Path | None = None) -> None:
    env = os.environ.copy()
    if path_prefix is not None:
        env["PATH"] = f"{path_prefix}{os.pathsep}{env.get('PATH', '')}"
    if log_path is None:
        subprocess.run(command, cwd=cwd, env=env, input=stdin_text, text=stdin_text is not None, check=True)
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(f"\n$ {' '.join(command)}\n")
        log_file.flush()
        subprocess.run(command, cwd=cwd, env=env, input=stdin_text, text=stdin_text is not None, stdout=log_file, stderr=subprocess.STDOUT, check=True)


def codex_log_path(config: Config, branch: str) -> Path:
    safe = branch.replace("/", "-")
    return config.logs_root / "codex" / f"{safe}.log"


def _rename_branch_from_codex_summary(
    config: Config,
    worktree_path: Path,
    bug: BugRecord,
    branch: str,
    log_path: Path | None,
) -> tuple[str, Path | None]:
    summary = generate_codex_change_summary(config, worktree_path, bug, config.target_app_path)
    next_branch = _available_codex_branch(config, branch_name_from_summary(bug.issue_id, summary), branch)
    if next_branch == branch:
        return branch, log_path
    rename_current_branch(worktree_path, next_branch)
    rename_task_state(config, branch, next_branch)
    if log_path is None:
        return next_branch, None
    next_log_path = codex_log_path(config, next_branch)
    if log_path.exists() and next_log_path != log_path:
        next_log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.replace(next_log_path)
    return next_branch, next_log_path


def _available_codex_branch(config: Config, desired_branch: str, current_branch: str) -> str:
    if desired_branch == current_branch or not branch_exists(config.target_repo, desired_branch):
        return desired_branch
    for index in range(2, 100):
        candidate = f"{desired_branch}-{index}"
        if not branch_exists(config.target_repo, candidate):
            return candidate
    return f"{desired_branch}-{datetime.now().strftime('%Y%m%d%H%M')}"


def _result(
    bug: BugRecord,
    status: str,
    branch: str,
    detail: str,
    image_paths: list[Path] | None = None,
    commit: str = "",
    changed_files: list[str] | None = None,
    diff_stat_text: str = "",
    log_path: Path | None = None,
) -> dict[str, Any]:
    return {
        "excel_row": bug.excel_row,
        "issue_id": bug.issue_id,
        "source_system": bug.source_system,
        "priority": bug.priority,
        "primary_category": bug.primary_category,
        "secondary_category": bug.secondary_category,
        "requester": bug.requester,
        "request_date": bug.request_date,
        "requester_status": bug.requester_status,
        "assignee": bug.assignee,
        "assignee_status": bug.assignee_status,
        "resolved_date": bug.resolved_date,
        "description": bug.description,
        "remark": bug.remark,
        "remark2": bug.remark2,
        "raw": bug.raw,
        "status": status,
        "branch": branch,
        "commit": commit,
        "changed_files": changed_files or [],
        "diff_stat": diff_stat_text,
        "detail": detail,
        "images": [str(path) for path in image_paths or []],
        "log_path": str(log_path) if log_path else "",
    }
