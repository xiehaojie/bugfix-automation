from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from bugfix_automation.api.dependencies import get_config
from bugfix_automation.application.log_service import log_event_stream, log_payload
from bugfix_automation.config import Config

router = APIRouter()


@router.get("/api/logs")
def get_logs(
    branch: str = "",
    offset: int | None = Query(default=None, ge=0),
    limit: int = Query(default=120000, ge=1, le=200000),
    config: Config = Depends(get_config),
):
    return log_payload(config, branch, offset=offset, limit=limit)


@router.get("/api/logs/stream")
def stream_logs(
    branch: str = "",
    limit: int = Query(default=120000, ge=1, le=200000),
    poll_interval: float = Query(default=0.5, ge=0.1, le=5),
    follow: bool = True,
    config: Config = Depends(get_config),
):
    return StreamingResponse(
        log_event_stream(config, branch, limit=limit, poll_interval=poll_interval, follow=follow),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
