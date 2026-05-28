from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from bugfix_automation.server.api.dependencies import get_config
from bugfix_automation.server.api.schemas import BranchRequest, FixValidationCommitRequest
from bugfix_automation.orchestration import fix_validation
from bugfix_automation.config import Config

router = APIRouter(prefix="/api/fix-validations", tags=["fix-validations"])


@router.get("/{branch:path}")
def get_fix_validation(branch: str, config: Config = Depends(get_config)):
    data = fix_validation.get_validation(config, branch)
    return {"ok": True, "validation": data}


@router.post("/{branch:path}/verify")
def verify_fix_validation(branch: str, config: Config = Depends(get_config)):
    try:
        data = fix_validation.verify(config, branch)
        return {"ok": True, "validation": data}
    except (ValueError, RuntimeError) as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)


@router.post("/{branch:path}/commit")
def commit_fix_validation(
    branch: str,
    payload: FixValidationCommitRequest,
    config: Config = Depends(get_config),
):
    try:
        data = fix_validation.commit_validation(config, branch, payload.location)
        return {"ok": True, "validation": data}
    except (ValueError, RuntimeError) as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)


@router.post("/{branch:path}/merge-to-target")
def merge_fix_validation_to_target(branch: str, config: Config = Depends(get_config)):
    try:
        data = fix_validation.merge_validation_to_target(config, branch)
        return {"ok": True, "validation": data}
    except (ValueError, RuntimeError) as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)


@router.post("/{branch:path}/revert")
def revert_fix_validation(branch: str, config: Config = Depends(get_config)):
    try:
        data = fix_validation.revert_validation(config, branch)
        return {"ok": True, "validation": data}
    except (FileNotFoundError, RuntimeError) as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)


@router.post("/{branch:path}/undo-commit")
def undo_fix_validation_commit(branch: str, config: Config = Depends(get_config)):
    try:
        data = fix_validation.undo_commit(config, branch)
        return {"ok": True, "validation": data}
    except (FileNotFoundError, RuntimeError) as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)


@router.post("/{branch:path}/remove-preview")
def remove_fix_validation_preview(branch: str, config: Config = Depends(get_config)):
    try:
        data = fix_validation.remove_preview(config, branch)
        return {"ok": True, "validation": data}
    except RuntimeError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)


@router.post("/{branch:path}/cleanup-source")
def cleanup_fix_validation_source(branch: str, config: Config = Depends(get_config)):
    try:
        data = fix_validation.cleanup_source(config, branch)
        return {"ok": True, "validation": data}
    except RuntimeError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)


@router.post("")
def get_fix_validation_from_body(payload: BranchRequest, config: Config = Depends(get_config)):
    data = fix_validation.get_validation(config, payload.branch)
    return {"ok": True, "validation": data}
