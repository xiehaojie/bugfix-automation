from __future__ import annotations

from pathlib import Path
import mimetypes

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, JSONResponse

from bugfix_automation.api.dependencies import get_config
from bugfix_automation.config import Config

router = APIRouter()


@router.get("/api/image")
def get_image(path: str = "", config: Config = Depends(get_config)):
    resolved = Path(path).expanduser().resolve()
    allowed_root = config.runs_root.resolve()
    if not resolved.is_file() or allowed_root not in [resolved, *resolved.parents]:
        return JSONResponse({"error": "图片不存在或不允许访问"}, status_code=404)
    media_type = mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
    return FileResponse(resolved, media_type=media_type)
