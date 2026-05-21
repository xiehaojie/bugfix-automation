from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import quote

from bugfix_automation.config import Config, active_workspace_config
from bugfix_automation.excel_writer import update_cell_by_header
from bugfix_automation.filtering import make_branch_name
from bugfix_automation.images import export_bug_images
from bugfix_automation.prompt import render_codex_prompt
from bugfix_automation.runner import list_bugs, run_one
from bugfix_automation.task_state import is_task_active, set_task_state, task_state


def bug_payload(config: Config) -> list[dict[str, Any]]:
    bugs = list_bugs(config)
    payload: list[dict[str, Any]] = []
    stamp = datetime.now().strftime("%Y%m%d%H%M")
    for bug in bugs:
        branch = make_branch_name(bug, config.branch_summary_fields, stamp)
        state = task_state(config, branch)
        images = export_bug_images(config.excel_path, bug, config.runs_root / "approval-images" / branch.replace("/", "-"))
        payload.append(
            {
                "issue_id": bug.issue_id,
                "excel_row": bug.excel_row,
                "branch": branch,
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
                "active": is_task_active(config, branch),
                "task_status": state.get("status", ""),
                "task_phase": state.get("phase", ""),
                "task_detail": state.get("detail", ""),
                "task_updated_at": state.get("updated_at", ""),
                "images": [
                    {"path": str(path), "name": path.name, "url": f"/api/image?path={quote(str(path), safe='')}"}
                    for path in images
                ],
            }
        )
    return payload


def start_bug_run(config: Config, excel_row: int) -> dict[str, Any]:
    bug = bug_by_row(config, excel_row)
    branch = make_branch_name(bug, config.branch_summary_fields, datetime.now().strftime("%Y%m%d%H%M"))
    if is_task_active(config, branch):
        state = task_state(config, branch)
        return {"ok": True, "branch": branch, "status": state.get("status", "running"), "message": "任务已在执行中"}
    set_task_state(config, branch, "queued", bug, detail="用户从审批台手动执行。", phase="queued")
    import threading

    thread = threading.Thread(target=run_one, args=(config,), kwargs={"excel_row": bug.excel_row}, daemon=True)
    thread.start()
    return {"ok": True, "branch": branch, "excel_row": bug.excel_row, "status": "queued"}


def delete_bug(config: Config, excel_row: int) -> dict[str, Any]:
    bug = bug_by_row(config, excel_row)
    branch = make_branch_name(bug, config.branch_summary_fields, datetime.now().strftime("%Y%m%d%H%M"))
    if is_task_active(config, branch):
        state = task_state(config, branch)
        raise RuntimeError(f"任务仍在执行中，不能删除：{state.get('status', '')}/{state.get('phase', '')}")
    update_cell_by_header(
        config.excel_path,
        config.sheet_name,
        bug.excel_row,
        config.excel_processed_status_column,
        config.excel_processed_status_value,
    )
    set_task_state(config, branch, "deleted", bug, detail="用户从审批台删除；Excel 已标记为已处理。", phase="done")
    return {"ok": True, "branch": branch, "excel_row": bug.excel_row}


def bug_by_row(config: Config, excel_row: int):
    if excel_row <= 0:
        raise ValueError("缺少 Excel 行号")
    for bug in list_bugs(config):
        if bug.excel_row == excel_row:
            return bug
    raise ValueError(f"当前筛选结果中没有 Excel 第 {excel_row} 行")


def preview_prompt(config: Config, excel_row: int) -> dict[str, Any]:
    bug = bug_by_row(config, excel_row)
    stamp = datetime.now().strftime("%Y%m%d%H%M")
    branch = make_branch_name(bug, config.branch_summary_fields, stamp)
    images = export_bug_images(
        config.excel_path, bug, config.runs_root / "approval-images" / branch.replace("/", "-")
    )
    workspace = active_workspace_config(config)
    prompt = render_codex_prompt(
        bug,
        target_app_path=config.target_app_path,
        prompt_fields=config.prompt_fields,
        prompt_template=config.prompt_template,
        context_paths=config.prompt_context_paths or None,
        workspace_name=workspace.name if workspace else "",
        image_paths=images,
        scope=workspace.scope if workspace else "frontend",
    )
    return {
        "ok": True,
        "excel_row": excel_row,
        "issue_id": bug.issue_id,
        "branch": branch,
        "prompt": prompt,
        "images": [
            {"path": str(path), "name": path.name, "url": f"/api/image?path={quote(str(path), safe='')}"}
            for path in images
        ],
    }


async def optimize_prompt(config: Config, excel_row: int, current_prompt: str) -> dict[str, Any]:
    """Use Codex in read-only mode to optimize/rewrite the given prompt."""
    import asyncio

    from bugfix_automation.prompt import PROMPTS_DIR

    try:
        bug = bug_by_row(config, excel_row)
    except Exception as exc:
        return {"ok": False, "error": f"查找 Bug 失败: {exc}"}

    template = (PROMPTS_DIR / "optimize.md").read_text(encoding="utf-8").strip()
    optimization_instruction = template.format(
        issue_id=bug.issue_id,
        description=bug.description,
        primary_category=bug.primary_category,
        secondary_category=bug.secondary_category,
        current_prompt=current_prompt,
    )
    try:
        proc = await asyncio.create_subprocess_exec(
            config.cli_tool, "exec", "-",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(optimization_instruction.encode()),
            timeout=120,
        )
        if proc.returncode != 0:
            err_msg = _extract_codex_error(stderr.decode(errors="replace"))
            return {"ok": False, "error": err_msg}
        optimized = stdout.decode(errors="replace").strip()
        if not optimized:
            return {"ok": False, "error": "CLI 工具未返回结果"}
        return {"ok": True, "prompt": optimized}
    except asyncio.TimeoutError:
        proc.kill()
        return {"ok": False, "error": "Codex 优化超时（120s）"}
    except OSError as exc:
        return {"ok": False, "error": f"Codex 调用失败: {exc}"}
    except Exception as exc:
        return {"ok": False, "error": f"优化失败: {type(exc).__name__}: {exc}"}


def _extract_codex_error(stderr: str) -> str:
    """Extract the most meaningful error line from codex stderr."""
    for line in reversed(stderr.splitlines()):
        if line.startswith("ERROR:"):
            return line.removeprefix("ERROR:").strip()
    return f"Codex 返回错误: {stderr[-200:]}" if stderr else "Codex 调用失败（未知错误）"
