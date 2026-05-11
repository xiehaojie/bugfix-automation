from __future__ import annotations

from datetime import date
import subprocess
from pathlib import Path
from typing import Any
import os

from bugfix_automation.config import Config
from bugfix_automation.excel_reader import read_sheet
from bugfix_automation.filtering import BugRecord, filter_bugs, make_branch_name
from bugfix_automation.images import export_bug_images
from bugfix_automation.prompt import render_codex_prompt
from bugfix_automation.reporter import write_reports
from bugfix_automation.worktree import (
    changed_paths,
    commit_all,
    create_no_push_git_wrapper,
    ensure_worktree,
    has_app_changes,
    install_project_agents,
    out_of_scope_paths,
    branch_exists,
    branch_worktree_path,
    worktree_path_for_branch,
    tracked_changed_files,
    diff_stat,
)


def list_bugs(config: Config) -> list[BugRecord]:
    rows = read_sheet(config.excel_path, config.sheet_name)
    return filter_bugs(rows, config.assignee)


def run_once(config: Config, dry_run: bool = False) -> tuple[Path, Path, Path]:
    bugs = list_bugs(config)
    run_dir = config.runs_root / date.today().isoformat()
    results: list[dict[str, Any]] = []
    for bug in bugs:
        branch = make_branch_name(bug)
        image_paths = export_bug_images(config.excel_path, bug, run_dir / "images" / branch.replace("/", "-"))
        if dry_run:
            results.append(_result(bug, "dry-run", branch, "Matched filters; no worktree or Codex invocation.", image_paths))
            continue
        results.append(process_bug(config, bug, branch, image_paths))
    return write_reports(run_dir, results)


def run_one(config: Config, issue_id: str | None = None, excel_row: int | None = None, dry_run: bool = False) -> tuple[Path, Path, Path]:
    bug = select_one_bug(list_bugs(config), issue_id=issue_id, excel_row=excel_row)
    run_dir = config.runs_root / date.today().isoformat() / f"single-row-{bug.excel_row}"
    branch = make_branch_name(bug)
    image_paths = export_bug_images(config.excel_path, bug, run_dir / "images" / branch.replace("/", "-"))
    if dry_run:
        result = _result(bug, "dry-run", branch, "Matched filters; single-bug dry-run only.", image_paths)
    else:
        result = process_bug(config, bug, branch, image_paths)
    return write_bug_results(run_dir, [result])


def select_one_bug(bugs: list[BugRecord], issue_id: str | None, excel_row: int | None) -> BugRecord:
    if not issue_id and excel_row is None:
        raise ValueError("Provide either issue_id or excel_row")
    matches = [
        bug
        for bug in bugs
        if (issue_id is not None and bug.issue_id == issue_id)
        or (excel_row is not None and bug.excel_row == excel_row)
    ]
    if not matches:
        raise ValueError("No matching bug found in filtered bug list")
    if len(matches) > 1:
        raise ValueError("Multiple matching bugs found; use --row for an exact Excel row")
    return matches[0]


def write_bug_results(run_dir: Path, results: list[dict[str, Any]]) -> tuple[Path, Path, Path]:
    return write_reports(run_dir, results)


def process_bug(config: Config, bug: BugRecord, branch: str, image_paths: list[Path]) -> dict[str, Any]:
    worktree_path: Path | None = None
    try:
        existing_path = worktree_path_for_branch(config.worktree_root, branch)
        if existing_path.exists():
            return _result(bug, "skipped", branch, f"Worktree already exists: {existing_path}", image_paths)
        existing_branch_path = branch_worktree_path(config.target_repo, branch)
        if existing_branch_path is not None:
            return _result(bug, "skipped", branch, f"Branch already checked out at: {existing_branch_path}", image_paths)
        if branch_exists(config.target_repo, branch):
            return _result(bug, "skipped", branch, "Branch already exists in target repository.", image_paths)
        worktree_path = ensure_worktree(config.target_repo, config.worktree_root, branch)
        install_project_agents(worktree_path, Path(__file__).resolve().parents[1])
        git_wrapper_dir = create_no_push_git_wrapper(worktree_path)
        prompt = render_codex_prompt(bug, config.target_app_path)
        _run(codex_command(config.codex_bin, str(worktree_path), prompt, image_paths), cwd=worktree_path, path_prefix=git_wrapper_dir, stdin_text=prompt)
        assert_scope_clean(changed_paths(worktree_path), config.target_app_path)
        _verify_frontend(worktree_path, config.target_app_path)
        assert_scope_clean(changed_paths(worktree_path), config.target_app_path)
        if not has_app_changes(worktree_path, config.target_app_path):
            return _result(bug, "no-change", branch, "Codex finished without local changes.", image_paths)
        changed_files = tracked_changed_files(worktree_path, config.target_app_path)
        commit = commit_all(worktree_path, _commit_message(bug))
        stat = diff_stat(worktree_path, f"{commit}~1", commit)
        return _result(
            bug,
            "committed",
            branch,
            f"Committed locally in {worktree_path}.",
            image_paths,
            commit=commit,
            changed_files=changed_files,
            diff_stat_text=stat,
        )
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"
        if worktree_path is not None:
            detail = f"{detail}; worktree={worktree_path}"
        return _result(bug, "failed", branch, detail, image_paths)


def codex_command(codex_bin: str, worktree_path: str, prompt: str, image_paths: list[Path] | None = None) -> list[str]:
    command = [
        codex_bin,
        "exec",
        "--sandbox",
        "workspace-write",
        "--cd",
        worktree_path,
    ]
    for image_path in image_paths or []:
        command.extend(["--image", str(image_path)])
    command.append("-")
    return command


def assert_scope_clean(paths: list[str], target_app_path: str) -> None:
    unsafe_paths = out_of_scope_paths(paths, target_app_path)
    if unsafe_paths:
        raise RuntimeError(f"Out-of-scope changes detected: {', '.join(unsafe_paths)}")


def _verify_frontend(worktree_path: Path, target_app_path: str) -> None:
    app_path = worktree_path / target_app_path
    _run(["npm", "run", "lint"], cwd=app_path)
    _run(["npm", "run", "build"], cwd=app_path)


def _run(command: list[str], cwd: Path, path_prefix: Path | None = None, stdin_text: str | None = None) -> None:
    env = os.environ.copy()
    if path_prefix is not None:
        env["PATH"] = f"{path_prefix}{os.pathsep}{env.get('PATH', '')}"
    subprocess.run(command, cwd=cwd, env=env, input=stdin_text, text=stdin_text is not None, check=True)


def _commit_message(bug: BugRecord) -> str:
    summary = bug.description.splitlines()[0][:60] or f"bug {bug.issue_id}"
    return f"fix(pc-web): {summary}\n\nExcel row: {bug.excel_row}\nIssue: {bug.issue_id}\nSource: {bug.source_system}"


def _result(
    bug: BugRecord,
    status: str,
    branch: str,
    detail: str,
    image_paths: list[Path] | None = None,
    commit: str = "",
    changed_files: list[str] | None = None,
    diff_stat_text: str = "",
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
    }
