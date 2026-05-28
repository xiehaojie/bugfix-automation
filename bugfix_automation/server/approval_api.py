from __future__ import annotations

import uvicorn

from bugfix_automation.server.api.app import create_app
from bugfix_automation.config import Config


def serve_api(config: Config, host: str = "127.0.0.1", port: int | None = None) -> None:
    api_port = port or config.approval_api_port
    print(f"审批 API 启动：http://{host}:{api_port}")
    uvicorn.run(create_app(), host=host, port=api_port, log_level="warning")
