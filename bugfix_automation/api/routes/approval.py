from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from bugfix_automation.api.dependencies import get_config
from bugfix_automation.api.schemas import BranchRequest, ReworkRequest
from bugfix_automation.application import approval_service
from bugfix_automation.config import Config
from bugfix_automation.worktree import branch_worktree_path, worktree_path_for_branch

router = APIRouter()


@router.get("/api/items")
def get_items(config: Config = Depends(get_config)):
    return approval_service.list_items(config)


@router.get("/api/file-content")
def get_file_content(
    branch: str = Query(...),
    path: str = Query(...),
    config: Config = Depends(get_config),
):
    """Return raw content of a file from a worktree branch."""
    # Resolve and guard against path traversal
    try:
        worktree_path = branch_worktree_path(config.target_repo, branch) or worktree_path_for_branch(
            config.worktree_root,
            branch,
        )
        file_path = worktree_path / path
        resolved = file_path.resolve()
        root = worktree_path.resolve()
        if root not in [resolved, *resolved.parents]:
            return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)
        if not resolved.is_file():
            return JSONResponse({"ok": False, "error": "not found"}, status_code=404)
        content = resolved.read_text(encoding="utf-8", errors="replace")
        return {"ok": True, "content": content}
    except Exception as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)


@router.post("/api/approve")
def post_approve(payload: BranchRequest, config: Config = Depends(get_config)):
    return {"ok": True, "commit": approval_service.approve(config, payload.branch)}


@router.post("/api/reject")
def post_reject(payload: BranchRequest, config: Config = Depends(get_config)):
    approval_service.reject(config, payload.branch)
    return {"ok": True}


@router.post("/api/cleanup")
def post_cleanup(payload: BranchRequest, config: Config = Depends(get_config)):
    approval_service.cleanup(config, payload.branch)
    return {"ok": True}


@router.post("/api/rework")
def post_rework(payload: ReworkRequest, config: Config = Depends(get_config)):
    from dataclasses import replace as dc_replace
    rework_config = dc_replace(config, cli_tool=payload.cli_tool) if payload.cli_tool else config
    approval_service.rework(
        rework_config,
        payload.branch,
        note=payload.note,
        file_paths=payload.file_paths,
        image_paths=payload.image_paths,
    )
    return {"ok": True}
