from __future__ import annotations

from pathlib import Path

from bugfix_automation.filtering import BugRecord


def render_codex_prompt(
    bug: BugRecord,
    target_app_path: str,
    prompt_fields: tuple[str, ...] | None = None,
    prompt_template: str = "",
    context_paths: tuple[str, ...] | None = None,
    workspace_name: str = "",
    image_paths: list[Path] | None = None,
) -> str:
    selected_fields = prompt_fields or tuple(key for key in bug.raw if key != "_excel_row")
    selected_lines = "\n".join(f"- {field}: {_field_value(bug, field)}" for field in selected_fields)
    context_lines = "\n".join(f"- {path}" for path in context_paths or () if path.strip()) or "- 无"
    image_lines = "\n".join(f"- {path}" for path in image_paths or []) or "- 无"
    return f"""你是本地自动化流程启动的 Codex。请使用项目级子智能体协同完成这个前端 bug 修复：

1. 先委派 bug-triage-agent 分析 Excel 行内容，判断是否属于前端问题，并定位可能区域。
2. 再委派 frontend-fix-agent 只修改 `{target_app_path}` 下的前端代码。
3. 再委派 verification-agent 运行验证并检查回归风险。
4. 最后委派 branch-commit-agent 整理本地分支状态、改动摘要和建议提交信息；不要自动提交。

硬性约束：
- 只允许修改 `{target_app_path}` 及其前端相关测试/配置。
- 不要修改后端、接口服务、数据库迁移或部署配置。
- 不要 push 到任何远端仓库。
- 不要自动 git commit；等待用户在审批台确认后再提交。
- 不要使用破坏性 git 命令。
- 修复后运行项目可用的 lint/build/test 验证。
- 如果判断该 bug 需要后端修改，请停止并在报告中说明，不要改后端。

Excel 信息：
- Excel 行号: {bug.excel_row}
- 序号: {bug.issue_id}
- 工作区: {workspace_name or target_app_path}

配置提示词：
{prompt_template or "无"}

Excel 选中字段：
{selected_lines}

随本次 Codex 调用传入的截图：
{image_lines}

需要优先阅读的工程文件/目录：
{context_lines}
"""


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
