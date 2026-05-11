from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Config:
    excel_path: Path
    sheet_name: str
    assignee: str
    target_repo: Path
    target_app_path: str
    worktree_root: Path
    runs_root: Path
    logs_root: Path
    launchd_label: str
    codex_bin: str
    schedule_hour: int
    schedule_minute: int
    approval_web_port: int
    approval_api_port: int


def load_config(config_path: Path | None = None) -> Config:
    repo_root = Path(__file__).resolve().parents[1]
    yaml_path = config_path or repo_root / "config.yaml"
    yaml_values = _read_config_yaml(yaml_path)

    def value(key: str, env_name: str, default: Any) -> Any:
        if env_name in os.environ:
            return os.environ[env_name]
        return yaml_values.get(key, default)

    target_repo = _path(value("target_repo", "BUGFIX_TARGET_REPO", "/Users/xiehaojie/code/monorepo"), repo_root)
    schedule = yaml_values.get("schedule", {})
    return Config(
        excel_path=_path(value("excel_path", "BUGFIX_EXCEL_PATH", "/Users/xiehaojie/Desktop/亦城数智人在线清单.xlsx"), repo_root),
        sheet_name=str(value("sheet_name", "BUGFIX_SHEET_NAME", "在线问题清单")),
        assignee=str(value("assignee", "BUGFIX_ASSIGNEE", "谢浩杰")),
        target_repo=target_repo,
        target_app_path=str(value("target_app_path", "BUGFIX_TARGET_APP_PATH", "apps/pc-web")),
        worktree_root=_path(value("worktree_root", "BUGFIX_WORKTREE_ROOT", repo_root / ".target-worktrees"), repo_root),
        runs_root=_path(value("runs_root", "BUGFIX_RUNS_ROOT", repo_root / "runs"), repo_root),
        logs_root=_path(value("logs_root", "BUGFIX_LOGS_ROOT", repo_root / "logs"), repo_root),
        launchd_label=str(value("launchd_label", "BUGFIX_LAUNCHD_LABEL", "local.bugfix-automation.nightly")),
        codex_bin=str(value("codex_bin", "BUGFIX_CODEX_BIN", "codex")),
        schedule_hour=int(os.environ.get("BUGFIX_SCHEDULE_HOUR", schedule.get("hour", 22))),
        schedule_minute=int(os.environ.get("BUGFIX_SCHEDULE_MINUTE", schedule.get("minute", 0))),
        approval_web_port=int(value("approval_web_port", "BUGFIX_APPROVAL_WEB_PORT", 8765)),
        approval_api_port=int(value("approval_api_port", "BUGFIX_APPROVAL_API_PORT", 8766)),
    )


def _path(raw: Any, repo_root: Path) -> Path:
    path = Path(str(raw)).expanduser()
    if path.is_absolute():
        return path
    return repo_root / path


def _read_config_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    values: dict[str, Any] = {}
    current_section: str | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if not line.startswith(" ") and line.endswith(":"):
            current_section = line[:-1].strip()
            values[current_section] = {}
            continue
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        key = key.strip()
        parsed = _parse_scalar(raw_value.strip())
        if raw_line.startswith(" ") and current_section:
            section = values.setdefault(current_section, {})
            if isinstance(section, dict):
                section[key] = parsed
        else:
            current_section = None
            values[key] = parsed
    return values


def _parse_scalar(value: str) -> str | int | bool:
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    if value.isdigit():
        return int(value)
    return value
