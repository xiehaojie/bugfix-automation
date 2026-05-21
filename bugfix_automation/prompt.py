from __future__ import annotations

from pathlib import Path

from bugfix_automation.filtering import BugRecord

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def _load_template(name: str) -> str:
    """Load a prompt template from the prompts/ directory."""
    path = PROMPTS_DIR / name
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    raise FileNotFoundError(f"Prompt template not found: {path}")


def render_codex_prompt(
    bug: BugRecord,
    target_app_path: str,
    prompt_fields: tuple[str, ...] | None = None,
    prompt_template: str = "",
    context_paths: tuple[str, ...] | None = None,
    workspace_name: str = "",
    image_paths: list[Path] | None = None,
    scope: str = "frontend",
) -> str:
    selected_fields = prompt_fields or tuple(key for key in bug.raw if key != "_excel_row")
    selected_lines = "\n".join(f"- {field}: {_field_value(bug, field)}" for field in selected_fields)
    raw_lines = "\n".join(
        f"- {field}: {value}"
        for field, value in bug.raw.items()
        if field != "_excel_row" and str(value).strip()
    ) or "- 无"
    context_lines = "\n".join(f"- {path}" for path in context_paths or () if path.strip()) or "- 无"
    image_lines = "\n".join(f"- {path}" for path in image_paths or []) or "- 无"

    template_map = {"frontend": "fix_frontend.md", "backend": "fix_backend.md", "fullstack": "fix_fullstack.md"}
    template_name = template_map.get(scope, "fix_frontend.md")
    template = _load_template(template_name)

    return template.format(
        target_app_path=target_app_path,
        excel_row=bug.excel_row,
        issue_id=bug.issue_id,
        workspace_name=workspace_name or target_app_path,
        prompt_template=prompt_template or "无",
        selected_lines=selected_lines,
        raw_lines=raw_lines,
        image_lines=image_lines,
        context_lines=context_lines,
    )


def _field_value(bug: BugRecord, field: str) -> str:
    formatted = {
        "序号": bug.issue_id,
        "来源系统": bug.source_system,
        "一级分类": bug.primary_category,
        "二级分类": bug.secondary_category,
        "优先级": bug.priority,
        "提出人": bug.requester,
        "提出日期": bug.request_date,
        "提出人状态": bug.requester_status,
        "对接人": bug.assignee,
        "对接人状态": bug.assignee_status,
        "解决日期": bug.resolved_date,
        "问题描述": bug.description,
        "备注": bug.remark,
        "备注2": bug.remark2,
    }
    return formatted.get(field, bug.raw.get(field, ""))
