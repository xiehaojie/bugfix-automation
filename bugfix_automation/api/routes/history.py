from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from bugfix_automation.api.dependencies import get_config
from bugfix_automation.application.history_service import (
    ai_session_log,
    list_ai_sessions,
    list_excel_imports,
    list_operations,
    operation_detail,
    operation_events,
)
from bugfix_automation.config import Config


router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("/operations")
def get_operations(limit: int = Query(default=100, ge=1, le=500), config: Config = Depends(get_config)):
    return list_operations(config, limit=limit)


@router.get("/operations/{operation_id}/events")
def get_operation_events(operation_id: str, config: Config = Depends(get_config)):
    return operation_events(config, operation_id)


@router.get("/operations/{operation_id}")
def get_operation_detail(operation_id: str, config: Config = Depends(get_config)):
    return operation_detail(config, operation_id)


@router.get("/excel-imports")
def get_excel_imports(limit: int = Query(default=50, ge=1, le=200), config: Config = Depends(get_config)):
    return list_excel_imports(config, limit=limit)


@router.get("/ai-sessions")
def get_ai_sessions(
    operation_id: str = "",
    limit: int = Query(default=50, ge=1, le=200),
    config: Config = Depends(get_config),
):
    return list_ai_sessions(config, operation_id=operation_id, limit=limit)


@router.get("/ai-sessions/{ai_session_id}/logs")
def get_ai_session_logs(
    ai_session_id: str,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=65536, ge=1, le=200000),
    config: Config = Depends(get_config),
):
    return ai_session_log(config, ai_session_id, offset=offset, limit=limit)
