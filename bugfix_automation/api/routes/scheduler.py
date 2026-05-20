from __future__ import annotations

from fastapi import APIRouter, Depends

from bugfix_automation.api.dependencies import get_config
from bugfix_automation.api.schemas import ScheduleInstallRequest
from bugfix_automation.application import scheduler_service
from bugfix_automation.config import Config

router = APIRouter()


@router.get("/api/scheduler")
def get_scheduler(config: Config = Depends(get_config)):
    return scheduler_service.status(config)


@router.post("/api/scheduler/install")
def post_scheduler_install(payload: ScheduleInstallRequest, config: Config = Depends(get_config)):
    return scheduler_service.install(config, payload.hour, payload.minute)


@router.post("/api/scheduler/uninstall")
def post_scheduler_uninstall(config: Config = Depends(get_config)):
    return scheduler_service.uninstall(config)


@router.post("/api/run-once")
def post_run_once(config: Config = Depends(get_config)):
    return scheduler_service.start_once(config)
