from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any


def write_reports(output_dir: Path, results: list[dict[str, Any]]) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = {"generated_at": datetime.now().isoformat(timespec="seconds"), "results": results}
    json_path = output_dir / "report.json"
    markdown_path = output_dir / "report.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(_markdown(results), encoding="utf-8")
    return json_path, markdown_path


def _markdown(results: list[dict[str, Any]]) -> str:
    lines = ["# Nightly Bugfix Automation Report", "", "| Issue | Status | Branch | Detail |", "| --- | --- | --- | --- |"]
    for result in results:
        lines.append(
            f"| {result.get('issue_id', '')} | {result.get('status', '')} | {result.get('branch', '')} | {result.get('detail', '')} |"
        )
    lines.append("")
    return "\n".join(lines)

