from __future__ import annotations

from pathlib import Path

# ── Default prompt configuration ──────────────────────────────────────────────

DEFAULT_PROMPT_FIELDS: tuple[str, ...] = (
    "序号",
    "来源系统",
    "一级分类",
    "二级分类",
    "优先级",
    "提出人",
    "提出日期",
    "提出人状态",
    "对接人",
    "对接人状态",
    "解决日期",
    "问题描述",
    "备注",
    "备注2",
)

DEFAULT_PROMPT_TEMPLATE = (
    "请优先修复前端可独立完成的问题；如果需要后端或数据改造，请停止并说明原因。\n"
    "修复后请在对应目录运行 lint 和 build，确保没有新增报错。\n"
    "如果修复涉及样式改动，请确认在常见分辨率下不会出现布局错位。"
)

# ── Prompt file paths ─────────────────────────────────────────────────────────

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

# ── Domain status values ──────────────────────────────────────────────────────

ALLOWED_SOURCE_SYSTEMS: set[str] = {"小亦PC", "小亦APP"}
ALLOWED_REQUESTER_STATUSES: set[str] = {"待处理", "处理中"}
SOLVED_STATUS = "已解决"

# ── Defaults ──────────────────────────────────────────────────────────────────

DEFAULT_ASSIGNEE = "谢浩杰"
DEFAULT_ACTIVE_WORKSPACE = "pc-web"
DEFAULT_MAX_CONCURRENCY = 2
DEFAULT_SCHEDULE_HOUR = 22
DEFAULT_SCHEDULE_MINUTE = 0
DEFAULT_LAUNCHD_LABEL = "local.bugfix-automation.nightly"
DEFAULT_APPROVAL_WEB_PORT = 8765
DEFAULT_APPROVAL_API_PORT = 8766
DEFAULT_EXCEL_SHEET_NAME = "在线问题清单"
DEFAULT_PROCESSED_STATUS_COLUMN = "对接人状态"
DEFAULT_PROCESSED_STATUS_VALUE = "已处理"
DEFAULT_VALIDATION_TARGET_BRANCHES: tuple[str, ...] = ("main", "master", "develop")
