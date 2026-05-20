from __future__ import annotations

from fastapi import APIRouter, Depends

from bugfix_automation.api.dependencies import get_config
from bugfix_automation.application.log_service import log_payload
from bugfix_automation.config import Config

router = APIRouter()


@router.get("/api/logs")
def get_logs(branch: str = "", config: Config = Depends(get_config)):
    return log_payload(config, branch)
