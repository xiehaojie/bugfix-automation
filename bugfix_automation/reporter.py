from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any


def write_reports(output_dir: Path, results: list[dict[str, Any]]) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    conflicts = conflict_index(results)
    payload = {"generated_at": datetime.now().isoformat(timespec="seconds"), "conflicts": conflicts, "results": results}
    json_path = output_dir / "report.json"
    markdown_path = output_dir / "report.md"
    approval_path = output_dir / "approval.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(_markdown(results, conflicts), encoding="utf-8")
    approval_path.write_text(_approval_markdown(results, conflicts), encoding="utf-8")
    return json_path, markdown_path, approval_path


def conflict_index(results: list[dict[str, Any]]) -> dict[str, list[str]]:
    file_to_issues: dict[str, list[str]] = {}
    for result in results:
        if result.get("status") != "committed":
            continue
        issue_id = str(result.get("issue_id", ""))
        for file_path in result.get("changed_files", []):
            file_to_issues.setdefault(file_path, []).append(issue_id)
    return {file_path: issues for file_path, issues in sorted(file_to_issues.items()) if len(issues) > 1}


def _markdown(results: list[dict[str, Any]], conflicts: dict[str, list[str]]) -> str:
    lines = ["# Nightly Bugfix Automation Report", "", "| Issue | Status | Branch | Images | Detail |", "| --- | --- | --- | --- | --- |"]
    for result in results:
        images = "<br>".join(result.get("images", []))
        lines.append(
            f"| {result.get('issue_id', '')} | {result.get('status', '')} | {result.get('branch', '')} | {images} | {result.get('detail', '')} |"
        )
    lines.append("")
    if conflicts:
        lines.extend(["## Conflict Risks", ""])
        for file_path, issues in conflicts.items():
            lines.append(f"- `{file_path}` touched by issues: {', '.join(issues)}")
        lines.append("")
    return "\n".join(lines)


def _approval_markdown(results: list[dict[str, Any]], conflicts: dict[str, list[str]]) -> str:
    lines = [
        "# Morning Approval Report",
        "",
        "Review these local branches before deciding which pc-web fixes to merge or cherry-pick. No branch has been pushed.",
        "",
    ]
    if conflicts:
        lines.extend(["## Conflict Risks", ""])
        for file_path, issues in conflicts.items():
            lines.append(f"- `{file_path}` is modified by bug(s): {', '.join(issues)}")
        lines.append("")
    else:
        lines.extend(["## Conflict Risks", "", "No committed fixes modify the same file.", ""])

    for result in results:
        lines.extend(
            [
                f"## Bug {result.get('issue_id', '')} - row {result.get('excel_row', '')}",
                "",
                f"- Status: `{result.get('status', '')}`",
                f"- Branch: `{result.get('branch', '')}`",
                f"- Commit: `{result.get('commit', '')}`",
                f"- Source: `{result.get('source_system', '')}`",
                f"- 一级分类: `{result.get('primary_category', '')}`",
                f"- 二级分类: `{result.get('secondary_category', '')}`",
                f"- 优先级: `{result.get('priority', '')}`",
                f"- 提出人: `{result.get('requester', '')}`",
                f"- 提出日期: `{result.get('request_date', '')}`",
                f"- 提出人状态: `{result.get('requester_status', '')}`",
                f"- 对接人: `{result.get('assignee', '')}`",
                f"- 对接人状态: `{result.get('assignee_status', '')}`",
                f"- 解决日期: `{result.get('resolved_date', '')}`",
                f"- 问题描述: {result.get('description', '')}",
                f"- 备注: {result.get('remark', '')}",
                f"- 备注2: {result.get('remark2', '')}",
                f"- Detail: {result.get('detail', '')}",
                "- Images:",
            ]
        )
        images = result.get("images", [])
        lines.extend([f"  - `{image}`" for image in images] or ["  - None"])
        lines.append("- Changed files:")
        lines.extend([f"  - `{file_path}`" for file_path in result.get("changed_files", [])] or ["  - None"])
        diff = result.get("diff_stat", "")
        if diff:
            lines.extend(["- Diff stat:", "", "```", diff, "```"])
        lines.append("")
    return "\n".join(lines)
