from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from bugfix_automation.api.dependencies import get_config
from bugfix_automation.api.schemas import BranchRequest, FixValidationCommitRequest, FixValidationVerifyRequest
from bugfix_automation.application import fix_validation_service
from bugfix_automation.config import Config

router = APIRouter(prefix="/api/fix-validations", tags=["fix-validations"])


@router.get("/{branch:path}/verify-log")
def get_fix_validation_verify_log(branch: str, config: Config = Depends(get_config)):
    try:
        content = fix_validation_service.get_verify_log(config, branch)
        return {"ok": True, "content": content}
    except (ValueError, RuntimeError) as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)


@router.get("/{branch:path}")
def get_fix_validation(branch: str, config: Config = Depends(get_config)):
    data = fix_validation_service.get_validation(config, branch)
    return {"ok": True, "validation": data}


@router.post("/{branch:path}/verify")
def verify_fix_validation(branch: str, payload: FixValidationVerifyRequest | None = None, config: Config = Depends(get_config)):
    try:
        commands_override: list[list[str]] | None = None
        if payload is not None:
            # 用户显式传了 payload：空列表 = 跳过验证，非空 = 使用用户指定命令
            commands_override = [cmd.split() for cmd in payload.verify_commands if cmd.strip()]
        data = fix_validation_service.verify(config, branch, commands_override=commands_override)
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
        data = fix_validation_service.commit_validation(config, branch, payload.location)
        return {"ok": True, "validation": data}
    except (ValueError, RuntimeError) as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)


@router.post("/{branch:path}/revert")
def revert_fix_validation(branch: str, config: Config = Depends(get_config)):
    try:
        data = fix_validation_service.revert_validation(config, branch)
        return {"ok": True, "validation": data}
    except (FileNotFoundError, RuntimeError) as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)


@router.post("/{branch:path}/undo-commit")
def undo_fix_validation_commit(branch: str, config: Config = Depends(get_config)):
    try:
        data = fix_validation_service.undo_commit(config, branch)
        return {"ok": True, "validation": data}
    except (FileNotFoundError, RuntimeError) as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)


@router.post("/{branch:path}/remove-preview")
def remove_fix_validation_preview(branch: str, config: Config = Depends(get_config)):
    try:
        data = fix_validation_service.remove_preview(config, branch)
        return {"ok": True, "validation": data}
    except RuntimeError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)


@router.post("/{branch:path}/cleanup-source")
def cleanup_fix_validation_source(branch: str, config: Config = Depends(get_config)):
    try:
        data = fix_validation_service.cleanup_source(config, branch)
        return {"ok": True, "validation": data}
    except RuntimeError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)


@router.post("")
def get_fix_validation_from_body(payload: BranchRequest, config: Config = Depends(get_config)):
    data = fix_validation_service.get_validation(config, payload.branch)
    return {"ok": True, "validation": data}
