from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from bugfix_automation.api.dependencies import get_config
from bugfix_automation.api.schemas import OnlineSheetRequest
from bugfix_automation.application import online_sheet_service
from bugfix_automation.config import Config
from bugfix_automation.integrations.online_sheets.registry import get_provider

router = APIRouter(prefix="/api/online-sheets", tags=["online-sheets"])


@router.get("/providers")
def list_providers():
    return online_sheet_service.list_online_sheet_providers()


@router.post("/preview")
def preview_online_sheet(payload: OnlineSheetRequest, config: Config = Depends(get_config)):
    try:
        provider = get_provider(payload.provider)
        return online_sheet_service.preview_online_sheet(
            config,
            provider_key=payload.provider,
            url=payload.url,
            range_address=payload.range,
            provider=provider,
        )
    except (ValueError, RuntimeError) as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)


@router.post("/import")
def import_online_sheet(payload: OnlineSheetRequest, config: Config = Depends(get_config)):
    try:
        provider = get_provider(payload.provider)
        return online_sheet_service.import_online_sheet(
            config,
            provider_key=payload.provider,
            url=payload.url,
            range_address=payload.range,
            provider=provider,
        )
    except (ValueError, RuntimeError) as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

