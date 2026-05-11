from __future__ import annotations

import os
from pathlib import Path
import plistlib
import subprocess
import shutil

from bugfix_automation.config import Config


def plist_path(config: Config) -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{config.launchd_label}.plist"


def plist_payload(config: Config) -> dict:
    repo_root = Path(__file__).resolve().parents[1]
    config.logs_root.mkdir(parents=True, exist_ok=True)
    env = {"PATH": os.environ.get("PATH", "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin")}
    env["BUGFIX_CODEX_BIN"] = resolve_codex_bin(config.codex_bin)
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


def resolve_codex_bin(codex_bin: str) -> str:
    candidate = Path(codex_bin).expanduser()
    if candidate.is_absolute():
        return str(candidate)
    found = shutil.which(codex_bin)
    if found:
        return found
    known = [
        Path.home() / ".nvm" / "versions" / "node" / "v24.14.1" / "bin" / codex_bin,
        Path("/opt/homebrew/bin") / codex_bin,
        Path("/usr/local/bin") / codex_bin,
    ]
    for path in known:
        if path.exists():
            return str(path)
    raise FileNotFoundError("没有找到 Codex CLI。请在 config.yaml 中配置 codex_bin，或设置 BUGFIX_CODEX_BIN 为绝对路径。")
