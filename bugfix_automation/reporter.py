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
    lines = ["# 夜间 Bug 自动修复报告", "", "| 序号 | 状态 | 分支 | 截图 | 说明 |", "| --- | --- | --- | --- | --- |"]
    for result in results:
        images = "<br>".join(result.get("images", []))
        lines.append(
            f"| {result.get('issue_id', '')} | {result.get('status', '')} | {result.get('branch', '')} | {images} | {result.get('detail', '')} |"
        )
    lines.append("")
    if conflicts:
        lines.extend(["## 冲突风险", ""])
        for file_path, issues in conflicts.items():
            lines.append(f"- `{file_path}` 被这些 bug 修改：{', '.join(issues)}")
        lines.append("")
    return "\n".join(lines)


def _approval_markdown(results: list[dict[str, Any]], conflicts: dict[str, list[str]]) -> str:
    lines = [
        "# 早上审批报告",
        "",
        "请先审查这些本地分支，再决定哪些 pc-web 修复可以提交。当前没有任何分支被 push。",
        "",
    ]
    if conflicts:
        lines.extend(["## 冲突风险", ""])
        for file_path, issues in conflicts.items():
            lines.append(f"- `{file_path}` 被这些 bug 修改：{', '.join(issues)}")
        lines.append("")
    else:
        lines.extend(["## 冲突风险", "", "没有发现多个已提交修复修改同一个文件。", ""])

    for result in results:
        lines.extend(
            [
                f"## Bug {result.get('issue_id', '')} - Excel 第 {result.get('excel_row', '')} 行",
                "",
                f"- 状态: `{result.get('status', '')}`",
                f"- 分支: `{result.get('branch', '')}`",
                f"- 提交: `{result.get('commit', '')}`",
                f"- 来源系统: `{result.get('source_system', '')}`",
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
                f"- 说明: {result.get('detail', '')}",
                "- 截图:",
            ]
        )
        images = result.get("images", [])
        lines.extend([f"  - `{image}`" for image in images] or ["  - 无"])
        lines.append("- 修改文件:")
        lines.extend([f"  - `{file_path}`" for file_path in result.get("changed_files", [])] or ["  - 无"])
        diff = result.get("diff_stat", "")
        if diff:
            lines.extend(["- Diff 统计:", "", "```", diff, "```"])
        lines.append("")
    return "\n".join(lines)
