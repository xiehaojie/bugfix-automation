from __future__ import annotations

import csv
from dataclasses import dataclass
import platform
from pathlib import Path
import shutil
import subprocess
import sys

from bugfix_automation.services.online_sheet_service import _table_to_xlsx_bytes
from bugfix_automation.domain.ai_cli import ai_cli_label, resolve_ai_cli_tool
from bugfix_automation.config import load_config, repo_root_path
from bugfix_automation.excel.reader import read_sheet
from bugfix_automation.integrations.online_sheets.base import SheetRef, SheetTable


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


def init_project(*, locale: str = "zh-CN", reset_config: bool = False, reset_runtime: bool = False, init_demo_repo: bool = True) -> list[str]:
    root = repo_root_path()
    messages: list[str] = []
    config_path = root / "config.yaml"
    normalized_locale = _normalize_locale(locale)
    example_config = root / ("config.example.en.yaml" if normalized_locale == "en" else "config.example.yaml")
    if reset_config or not config_path.exists():
        shutil.copyfile(example_config, config_path)
        messages.append(f"wrote {config_path.relative_to(root)}")
    else:
        messages.append(f"kept existing {config_path.relative_to(root)}")

    runtime_db = root / "data" / "app.sqlite3"
    if reset_runtime and runtime_db.exists():
        runtime_db.unlink()
        messages.append(f"removed runtime settings {runtime_db.relative_to(root)}")

    examples_dir = root / "examples"
    examples_dir.mkdir(exist_ok=True)
    for demo_locale, sheet_name in (("zh-CN", "Bug清单"), ("en", "Bugs")):
        suffix = "zh-CN" if demo_locale == "zh-CN" else "en"
        xlsx_path = examples_dir / f"bugs.{suffix}.xlsx"
        csv_path = examples_dir / f"bugs.{suffix}.csv"
        if reset_config or not xlsx_path.exists():
            _write_demo_xlsx(csv_path, xlsx_path, sheet_name)
            messages.append(f"wrote {xlsx_path.relative_to(root)}")
        else:
            messages.append(f"kept existing {xlsx_path.relative_to(root)}")

    config = load_config(config_path)
    config.data_root.mkdir(parents=True, exist_ok=True)
    rows = read_sheet(config.excel_path, config.sheet_name)
    messages.append(f"demo bug rows: {len(rows)}")

    if init_demo_repo:
        messages.extend(_ensure_demo_target_repo(root / "examples" / "demo-target-repo"))
    return messages


def doctor() -> list[CheckResult]:
    root = repo_root_path()
    results = [
        CheckResult("python", True, platform.python_version()),
        _command_check("git", ["git", "--version"], required=True),
        _command_check("node", ["node", "--version"], required=False),
        _command_check("npm", [_npm_command(), "--version"], required=False),
    ]
    try:
        config = load_config()
        cli_name = ai_cli_label(config.cli_tool).lower().replace(" ", "_")
        results.append(_command_check(cli_name, [resolve_ai_cli_tool(config.cli_tool), "--version"], required=False))
        results.append(CheckResult("config", True, str(root / "config.yaml")))
        results.append(CheckResult("excel", config.excel_path.exists(), str(config.excel_path)))
        results.append(CheckResult("target_repo", (config.target_repo / ".git").exists(), str(config.target_repo)))
        results.append(CheckResult("target_app_path", (config.target_repo / config.target_app_path).exists(), config.target_app_path))
    except Exception as exc:
        results.append(CheckResult("config", False, f"{type(exc).__name__}: {exc}"))
    return results


def print_check_results(results: list[CheckResult]) -> int:
    failed_required = False
    for result in results:
        marker = "OK" if result.ok else "WARN"
        print(f"[{marker}] {result.name}: {result.detail}")
        if result.name in {"python", "git", "config"} and not result.ok:
            failed_required = True
    return 1 if failed_required else 0


def _write_demo_xlsx(csv_path: Path, xlsx_path: Path, sheet_name: str) -> None:
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        rows = [dict(row) for row in reader]
    table = SheetTable(
        ref=SheetRef(provider="demo", source_url=str(csv_path), workbook_id="bugs"),
        range_address="A1:Z1000",
        headers=headers,
        rows=rows,
    )
    xlsx_path.write_bytes(_table_to_xlsx_bytes(table, sheet_name))


def _normalize_locale(locale: str) -> str:
    text = locale.strip().lower().replace("_", "-")
    if text in {"en", "en-us", "english"}:
        return "en"
    return "zh-CN"


def _ensure_demo_target_repo(path: Path) -> list[str]:
    messages: list[str] = []
    if (path / ".git").exists():
        messages.append(f"kept existing {path.name} git repository")
        return messages
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "add", "."], cwd=path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Demo Bootstrap",
            "-c",
            "user.email=demo@example.invalid",
            "commit",
            "-m",
            "Initial demo target app",
        ],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    )
    messages.append(f"initialized {path.name} git repository")
    return messages


def _command_check(name: str, command: list[str], *, required: bool) -> CheckResult:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as exc:
        detail = f"{type(exc).__name__}: {exc}"
        return CheckResult(name, False if required else False, detail)
    output = (result.stdout or result.stderr).strip().splitlines()
    detail = output[0] if output else f"exit {result.returncode}"
    return CheckResult(name, result.returncode == 0, detail)


def _npm_command() -> str:
    return "npm.cmd" if sys.platform.startswith("win") else "npm"
