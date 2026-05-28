from __future__ import annotations

from bugfix_automation.config import Config, load_config
from bugfix_automation.scheduling.scheduler import install_launchd_at, launchd_status, start_manual_run, uninstall_launchd
from bugfix_automation.storage.settings import get_setting, set_setting


def status(config: Config) -> dict:
    return launchd_status(config)


def install(config: Config, hour: int, minute: int) -> dict:
    automation = get_setting(config.storage_db_path, "automation", {})
    if not isinstance(automation, dict):
        automation = {}
    set_setting(config.storage_db_path, "automation", {**automation, "schedule": {"hour": hour, "minute": minute}})
    next_config = load_config()
    path = install_launchd_at(next_config, hour, minute)
    return {"ok": True, "plist_path": str(path), "status": launchd_status(next_config)}


def uninstall(config: Config) -> dict:
    result = uninstall_launchd(config)
    return {"ok": True, "result": result, "status": launchd_status(load_config())}


def start_once(config: Config) -> dict:
    return {"ok": True, "run": start_manual_run(config)}
