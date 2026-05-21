from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import re
import unicodedata

from bugfix_automation.config import CanonicalFieldMapping, FilterRule


ALLOWED_SOURCE_SYSTEMS = {"小亦PC", "小亦APP"}
ALLOWED_REQUESTER_STATUSES = {"待处理", "处理中"}
SOLVED_STATUS = "已解决"


@dataclass(frozen=True)
class BugRecord:
    excel_row: int
    issue_id: str
    requester_status: str
    source_system: str
    priority: str
    primary_category: str
    secondary_category: str
    requester: str
    request_date: str
    assignee: str
    assignee_status: str
    resolved_date: str
    description: str
    remark: str
    remark2: str
    raw: dict[str, str]


def filter_bugs(
    rows: list[dict[str, str]],
    assignee: str,
    excluded_assignee_statuses: set[str] | None = None,
    rules: tuple[FilterRule, ...] | None = None,
    mapping: CanonicalFieldMapping | None = None,
) -> list[BugRecord]:
    closed_statuses = {SOLVED_STATUS}
    if excluded_assignee_statuses:
        closed_statuses.update(status.strip() for status in excluded_assignee_statuses if status.strip())

    bugs: list[BugRecord] = []
    for row in rows:
        if rules:
            if not _matches_rules(row, rules):
                continue
        else:
            if _clean(row.get("对接人")) != assignee:
                continue
            if _clean(row.get("对接人状态")) in closed_statuses:
                continue
            if _clean(row.get("来源系统")) not in ALLOWED_SOURCE_SYSTEMS:
                continue
            if _clean(row.get("提出人状态")) not in ALLOWED_REQUESTER_STATUSES:
                continue
        bugs.append(bug_record_from_row(row, mapping))
    return bugs


def bug_record_from_row(row: dict[str, str], mapping: CanonicalFieldMapping | None = None) -> BugRecord:
    fields = mapping or CanonicalFieldMapping()
    return BugRecord(
        excel_row=int(row.get("_excel_row", "0") or "0"),
        issue_id=_clean(row.get(fields.issue_id)) or str(row.get("_excel_row", "")),
        requester_status=_clean(row.get(fields.requester_status)),
        source_system=_clean(row.get(fields.source_system)),
        priority=_clean(row.get(fields.priority)),
        primary_category=_clean(row.get(fields.primary_category)),
        secondary_category=_clean(row.get(fields.secondary_category)),
        requester=_clean(row.get(fields.requester)),
        request_date=_format_excel_date(row.get(fields.request_date)),
        assignee=_clean(row.get(fields.assignee)),
        assignee_status=_clean(row.get(fields.assignee_status)),
        resolved_date=_format_excel_date(row.get(fields.resolved_date)),
        description=_clean(row.get(fields.description)),
        remark=_clean(row.get(fields.remark)),
        remark2=_clean(row.get(fields.remark2)),
        raw=row,
    )


def _matches_rules(row: dict[str, str], rules: tuple[FilterRule, ...]) -> bool:
    for rule in rules:
        cell = _clean(row.get(rule.field))
        cell_values = _split_cell_values(cell)
        values = set(rule.values or ((rule.value,) if rule.value else ()))
        if rule.op == "equals" and cell != rule.value:
            return False
        if rule.op == "not_equals" and cell == rule.value:
            return False
        if rule.op == "in" and cell not in values:
            return False
        if rule.op == "any_in" and not values.intersection(cell_values):
            return False
        if rule.op == "all_in" and (not cell_values or not cell_values.issubset(values)):
            return False
        if rule.op == "not_in" and (cell in values or values.intersection(cell_values)):
            return False
        if rule.op == "non_empty" and not cell:
            return False
        if rule.op == "empty" and cell:
            return False
    return True


def make_branch_name(
    bug: BugRecord,
    summary_fields: tuple[str, ...] | None = None,
    timestamp: str | datetime | None = None,
) -> str:
    summary = _summary_from_fields(bug, ("问题描述",) if summary_fields is None else summary_fields)
    stamp = _format_branch_stamp(timestamp or datetime.now())
    return f"fix/bug-{bug.issue_id}-{summary}-{stamp}"


def _clean(value: str | None) -> str:
    return (value or "").strip()


def _split_cell_values(value: str) -> set[str]:
    return {part.strip() for part in re.split(r"[,，、;；\n]+", value) if part.strip()}


def _summary_from_fields(bug: BugRecord, fields: tuple[str, ...]) -> str:
    parts = [bug.raw.get(field, "") for field in fields if bug.raw.get(field, "").strip()]
    joined = " ".join(parts) or bug.description or bug.remark or bug.secondary_category or bug.primary_category
    summary = _chinese_summary(joined) or _slugify(joined)
    return summary or f"row-{bug.excel_row}"


def _format_branch_stamp(value: str | datetime) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y%m%d%H%M")
    text = str(value).strip()
    if re.fullmatch(r"\d{12}", text):
        return text
    return datetime.now().strftime("%Y%m%d%H%M")


def _format_excel_date(value: str | None) -> str:
    cleaned = _clean(value)
    if not cleaned:
        return ""
    try:
        serial = float(cleaned)
    except ValueError:
        return cleaned
    if serial <= 0:
        return cleaned
    date_value = datetime(1899, 12, 30) + timedelta(days=serial)
    return f"{date_value.year}/{date_value.month}/{date_value.day}"


PINYIN = {
    "账": "zhang",
    "号": "hao",
    "离": "li",
    "线": "xian",
    "状": "zhuang",
    "态": "tai",
    "异": "yi",
    "常": "chang",
}


def _slugify(value: str) -> str:
    parts: list[str] = []
    for char in unicodedata.normalize("NFKC", value).lower():
        if char.isascii() and char.isalnum():
            parts.append(char)
        elif char in PINYIN:
            parts.extend(["-", PINYIN[char], "-"])
        else:
            parts.append("-")
    return re.sub(r"-+", "-", "".join(parts)).strip("-")


def _chinese_summary(value: str) -> str:
    text = unicodedata.normalize("NFKC", value)
    text = re.split(r"[；;。]", text, maxsplit=1)[0]
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[，。；;,.、/\\（）()【】\[\]「」“”\"'：:\s]+", "", text)
    text = text.replace("在", "", 1)
    text = text.replace("后", "")
    text = text.replace("另外", "")
    text = text.replace("建议", "")
    text = text.replace("目前", "")
    text = text.replace("页面中间", "")
    text = text.replace("暂无上传文件", "")
    text = text.replace("上面的", "")
    text = text.replace("或者", "")
    text = text.replace("点击", "")
    text = re.split(r"没有|需|建议", text, maxsplit=1)[0]
    return text[:18]
