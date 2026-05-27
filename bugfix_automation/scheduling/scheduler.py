from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import os
from pathlib import Path
import plistlib
import subprocess
import shutil
import sys

from bugfix_automation.config import Config


def plist_path(config: Config) -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{config.launchd_label}.plist"


def plist_payload(config: Config) -> dict:
    repo_root = Path(__file__).resolve().parents[1]
    config.logs_root.mkdir(parents=True, exist_ok=True)
    env = {"PATH": os.environ.get("PATH", "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin")}
    env["BUGFIX_CLI_TOOL"] = resolve_cli_tool(config.cli_tool)
    return {
        "Label": config.launchd_label,
        "ProgramArguments": ["/usr/bin/python3", "-m", "bugfix_automation.cli", "run-once"],
        "WorkingDirectory": str(repo_root),
        "StartCalendarInterval": {"Hour": config.schedule_hour, "Minute": config.schedule_minute},
        "StandardOutPath": str(config.logs_root / "launchd.out.log"),
        "StandardErrorPath": str(config.logs_root / "launchd.err.log"),
        "EnvironmentVariables": env,
        "RunAtLoad": False,
    }


def install_launchd(config: Config) -> Path:
    path = plist_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(plistlib.dumps(plist_payload(config)))
    subprocess.run(["launchctl", "unload", str(path)], check=False)
    subprocess.run(["launchctl", "load", str(path)], check=True)
    return path


def install_launchd_at(config: Config, hour: int, minute: int) -> Path:
    _validate_time(hour, minute)
    return install_launchd(replace(config, schedule_hour=hour, schedule_minute=minute))


def uninstall_launchd(config: Config) -> dict:
    path = plist_path(config)
    unloaded = subprocess.run(["launchctl", "unload", str(path)], check=False)
    removed = False
    if path.exists():
        path.unlink()
        removed = True
    return {"ok": True, "unloaded": unloaded.returncode == 0, "removed": removed, "plist_path": str(path)}


def launchd_status(config: Config) -> dict:
    path = plist_path(config)
    loaded = False
    detail = ""
    schedule_hour = config.schedule_hour
    schedule_minute = config.schedule_minute
    if path.exists():
        schedule_hour, schedule_minute = _plist_schedule(path, config.schedule_hour, config.schedule_minute)
        result = subprocess.run(
            ["launchctl", "print", f"gui/{os.getuid()}/{config.launchd_label}"],
            text=True,
            capture_output=True,
            check=False,
        )
        loaded = result.returncode == 0
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        if stderr:
            detail = stderr
        elif stdout:
            detail = stdout.splitlines()[0]
    return {
        "label": config.launchd_label,
        "plist_path": str(path),
        "installed": path.exists(),
        "loaded": loaded,
        "detail": detail,
        "schedule_hour": schedule_hour,
        "schedule_minute": schedule_minute,
        "stdout_log": str(config.logs_root / "launchd.out.log"),
        "stderr_log": str(config.logs_root / "launchd.err.log"),
    }


def start_manual_run(config: Config) -> dict:
    repo_root = Path(__file__).resolve().parents[1]
    config.logs_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = config.logs_root / f"manual-run-{stamp}.log"
    log_file = log_path.open("ab")
    process = subprocess.Popen(
        [sys.executable, "-m", "bugfix_automation.cli", "run-once"],
        cwd=repo_root,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    log_file.close()
    return {"pid": process.pid, "log_path": str(log_path)}


def resolve_cli_tool(cli_tool: str) -> str:
    candidate = Path(cli_tool).expanduser()
    if candidate.is_absolute():
        return str(candidate)
    found = shutil.which(cli_tool)
    if found:
        return found
    known = [
        Path.home() / ".nvm" / "versions" / "node" / "v24.14.1" / "bin" / cli_tool,
        Path("/opt/homebrew/bin") / cli_tool,
        Path("/usr/local/bin") / cli_tool,
    ]
    for path in known:
        if path.exists():
            return str(path)
    raise FileNotFoundError(f"没有找到 CLI 工具 '{cli_tool}'。请在 config.yaml 中配置 cli_tool，或设置 BUGFIX_CLI_TOOL 为绝对路径。")



def _plist_schedule(path: Path, default_hour: int, default_minute: int) -> tuple[int, int]:
    try:
        payload = plistlib.loads(path.read_bytes())
    except (OSError, plistlib.InvalidFileException):
        return default_hour, default_minute
    interval = payload.get("StartCalendarInterval", {})
    if not isinstance(interval, dict):
        return default_hour, default_minute
    try:
        return int(interval.get("Hour", default_hour)), int(interval.get("Minute", default_minute))
    except (TypeError, ValueError):
        return default_hour, default_minute


def _validate_time(hour: int, minute: int) -> None:
    if hour < 0 or hour > 23:
        raise ValueError("小时必须在 0-23 之间")
    if minute < 0 or minute > 59:
        raise ValueError("分钟必须在 0-59 之间")
