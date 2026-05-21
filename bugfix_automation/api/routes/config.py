from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from bugfix_automation.ai_cli import ai_cli_kind, ai_cli_print_command
from bugfix_automation.api.dependencies import get_config
from bugfix_automation.api.schemas import ConfigUpdateRequest, FiltersUpdateRequest, WorkspaceAddRequest, WorkspaceRemoveRequest, WorkspaceSelectRequest
from bugfix_automation.application.config_service import add_workspace, config_payload, remove_workspace, select_workspace, update_automation_config, update_filters
from bugfix_automation.config import Config

router = APIRouter()


@router.get("/api/config")
def get_config_payload(config: Config = Depends(get_config)):
    return config_payload(config)


@router.get("/api/browse-dirs")
def browse_dirs(path: str = Query("~")):
    """List subdirectories for folder picker."""
    base = Path(path).expanduser().resolve()
    if not base.is_dir():
        return {"ok": False, "error": "路径不存在", "dirs": [], "current": str(base)}
    dirs: list[dict[str, str]] = []
    try:
        for entry in sorted(base.iterdir()):
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                dirs.append({"name": entry.name, "path": str(entry)})
    except PermissionError:
        pass
    return {"ok": True, "current": str(base), "parent": str(base.parent), "dirs": dirs}


@router.post("/api/workspace/select")
def post_workspace_select(payload: WorkspaceSelectRequest, config: Config = Depends(get_config)):
    return select_workspace(config, payload.workspace_id)


@router.post("/api/workspace/add")
def post_workspace_add(payload: WorkspaceAddRequest):
    return add_workspace(payload.model_dump())


@router.post("/api/workspace/remove")
def post_workspace_remove(payload: WorkspaceRemoveRequest):
    return remove_workspace(payload.workspace_id)


@router.post("/api/config/update")
def post_config_update(payload: ConfigUpdateRequest):
    return update_automation_config(payload.model_dump(exclude_none=True))


@router.post("/api/filters/update")
def post_filters_update(payload: FiltersUpdateRequest):
    return update_filters([rule.model_dump() for rule in payload.filters])


class CliTestRequest(BaseModel):
    cli_tool: str = ""


@router.post("/api/cli/test")
async def post_cli_test(payload: CliTestRequest, config: Config = Depends(get_config)):
    tool = payload.cli_tool.strip() or config.cli_tool
    test_prompt = "Reply with exactly: CONNECTED"
    try:
        if ai_cli_kind(tool) == "claude":
            proc = await asyncio.create_subprocess_exec(
                *ai_cli_print_command(tool),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(test_prompt.encode()), timeout=30)
        else:
            proc = await asyncio.create_subprocess_exec(
                *ai_cli_print_command(tool),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(test_prompt.encode()),
                timeout=30,
            )
        if proc.returncode == 0:
            output = stdout.decode(errors="replace").strip()
            return {"ok": True, "version": output[:100] or "连接成功"}
        err = stderr.decode(errors="replace").strip()
        return {"ok": False, "error": err[:200] or f"退出码 {proc.returncode}"}
    except FileNotFoundError:
        return {"ok": False, "error": f"未找到命令: {tool}"}
    except asyncio.TimeoutError:
        return {"ok": False, "error": "请求超时（30s），请检查网络或 API Key 配置"}
