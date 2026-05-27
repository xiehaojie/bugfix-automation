from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from bugfix_automation.server.api.dependencies import get_config
from bugfix_automation.server.api.schemas import IntegrationCreateRequest
from bugfix_automation.orchestration import integration
from bugfix_automation.config import Config

router = APIRouter(prefix="/api/integration-runs", tags=["integration"])


@router.get("")
def list_integration_runs(config: Config = Depends(get_config)):
    runs = integration.list_runs(config)
    return {"ok": True, "runs": runs}


@router.get("/branches")
def list_available_branches(config: Config = Depends(get_config)):
    branches = integration.available_fix_branches(config)
    return {"ok": True, "branches": branches}


@router.get("/target-branches")
def list_target_branches(config: Config = Depends(get_config)):
    data = integration.target_branches(config)
    return {"ok": True, **data}


@router.get("/{run_id}")
def get_integration_run(run_id: str, config: Config = Depends(get_config)):
    try:
        data = integration.get_run(config, run_id)
        return {"ok": True, "run": data}
    except FileNotFoundError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=404)


@router.get("/{run_id}/diff")
def get_integration_diff(run_id: str, config: Config = Depends(get_config)):
    try:
        diff = integration.get_run_diff(config, run_id)
        return {"ok": True, "diff": diff}
    except FileNotFoundError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=404)


@router.post("")
def create_integration_run(payload: IntegrationCreateRequest, config: Config = Depends(get_config)):
    try:
        data = integration.create_run(
            config,
            workspace_id=payload.workspace_id,
            target_branch=payload.target_branch,
            branches=payload.branches,
        )
        return {"ok": True, "run": data}
    except (ValueError, RuntimeError) as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)


@router.post("/{run_id}/start")
def start_integration_run(run_id: str, config: Config = Depends(get_config)):
    try:
        data = integration.start_run(config, run_id)
        return {"ok": True, "run": data}
    except (FileNotFoundError, RuntimeError) as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)


@router.post("/{run_id}/confirm")
def confirm_integration_run(run_id: str, config: Config = Depends(get_config)):
    try:
        data = integration.confirm_run(config, run_id)
        return {"ok": True, "run": data}
    except (FileNotFoundError, RuntimeError) as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)


@router.post("/{run_id}/cleanup")
def cleanup_integration_run(run_id: str, config: Config = Depends(get_config)):
    try:
        data = integration.cleanup_run(config, run_id)
        return {"ok": True, "run": data}
    except (FileNotFoundError, RuntimeError) as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)


@router.post("/{run_id}/abort")
def abort_integration_run(run_id: str, config: Config = Depends(get_config)):
    try:
        data = integration.abort_run(config, run_id)
        return {"ok": True, "run": data}
    except (FileNotFoundError, RuntimeError) as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)


@router.delete("/{run_id}")
def delete_integration_run(run_id: str, config: Config = Depends(get_config)):
    try:
        data = integration.delete_run(config, run_id)
        return {"ok": True, **data}
    except FileNotFoundError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=404)
    except RuntimeError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
