from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from bugfix_automation.server.api.errors import json_error_handler
from bugfix_automation.server.api.routes import approval, bugs, config as config_routes, excel, fix_validations, history, integration, logs, online_sheets, scheduler, static_files
from bugfix_automation.config import Config


def create_app(config: Config | None = None) -> FastAPI:
    app = FastAPI(title="Bugfix Automation Approval API")
    app.state.config = config
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            f"http://127.0.0.1:{config.approval_web_port}",
            f"http://localhost:{config.approval_web_port}",
        ] if config else [],
        allow_origin_regex=r"^http://(127\.0\.0\.1|localhost):\d+$",
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    app.add_exception_handler(Exception, json_error_handler)
    for router in (
        approval.router,
        bugs.router,
        config_routes.router,
        excel.router,
        fix_validations.router,
        history.router,
        integration.router,
        logs.router,
        online_sheets.router,
        scheduler.router,
        static_files.router,
    ):
        app.include_router(router)
    return app
