from __future__ import annotations

from bugfix_automation.config import Config, load_config, update_config_yaml
from bugfix_automation.scheduler import install_launchd_at, launchd_status, start_manual_run, uninstall_launchd


def status(config: Config) -> dict:
    return launchd_status(config)


def install(config: Config, hour: int, minute: int) -> dict:
    update_config_yaml({"schedule": {"hour": hour, "minute": minute}})
    next_config = load_config()
    path = install_launchd_at(next_config, hour, minute)
    return {"ok": True, "plist_path": str(path), "status": launchd_status(next_config)}


def uninstall(config: Config) -> dict:
    result = uninstall_launchd(config)
    return {"ok": True, "result": result, "status": launchd_status(load_config())}


def start_once(config: Config) -> dict:
    return {"ok": True, "run": start_manual_run(config)}
