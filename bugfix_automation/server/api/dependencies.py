from __future__ import annotations

from fastapi import Request

from bugfix_automation.config import Config, load_config


def get_config(request: Request) -> Config:
    config = getattr(request.app.state, "config", None)
    if config is not None:
        return config
    return load_config()
