from __future__ import annotations

from fastapi import APIRouter, Depends

from bugfix_automation.api.dependencies import get_config
from bugfix_automation.api.schemas import BugRowRequest, OptimizePromptRequest
from bugfix_automation.application.bug_service import bug_payload, delete_bug, optimize_prompt, preview_prompt, start_bug_run
from bugfix_automation.config import Config

router = APIRouter()


@router.get("/api/bugs")
def get_bugs(config: Config = Depends(get_config)):
    return {"bugs": bug_payload(config)}


@router.post("/api/bugs/run")
def post_bug_run(payload: BugRowRequest, config: Config = Depends(get_config)):
    return start_bug_run(config, payload.excel_row)


@router.post("/api/bugs/delete")
def post_bug_delete(payload: BugRowRequest, config: Config = Depends(get_config)):
    return delete_bug(config, payload.excel_row)


@router.post("/api/bugs/preview-prompt")
def post_bug_preview_prompt(payload: BugRowRequest, config: Config = Depends(get_config)):
    return preview_prompt(config, payload.excel_row)


@router.post("/api/bugs/optimize-prompt")
async def post_bug_optimize_prompt(payload: OptimizePromptRequest, config: Config = Depends(get_config)):
    return await optimize_prompt(config, payload.excel_row, payload.prompt)
