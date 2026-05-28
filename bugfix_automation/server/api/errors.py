from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse


async def json_error_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, status_code=500)
