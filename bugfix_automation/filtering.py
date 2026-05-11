from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import re
import unicodedata


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


def filter_bugs(rows: list[dict[str, str]], assignee: str) -> list[BugRecord]:
    bugs: list[BugRecord] = []
    for row in rows:
        if _clean(row.get("对接人")) != assignee:
            continue
        if _clean(row.get("对接人状态")) == SOLVED_STATUS:
            continue
        if _clean(row.get("来源系统")) not in ALLOWED_SOURCE_SYSTEMS:
            continue
        if _clean(row.get("提出人状态")) not in ALLOWED_REQUESTER_STATUSES:
            continue
        bugs.append(
            BugRecord(
                excel_row=int(row.get("_excel_row", "0") or "0"),
                issue_id=_clean(row.get("序号")) or str(row.get("_excel_row", "")),
                requester_status=_clean(row.get("提出人状态")),
                source_system=_clean(row.get("来源系统")),
                priority=_clean(row.get("优先级")),
                primary_category=_clean(row.get("一级分类")),
                secondary_category=_clean(row.get("二级分类")),
                requester=_clean(row.get("提出人")),
                request_date=_format_excel_date(row.get("提出日期")),
                assignee=_clean(row.get("对接人")),
                assignee_status=_clean(row.get("对接人状态")),
                resolved_date=_format_excel_date(row.get("解决日期")),
                description=_clean(row.get("问题描述")),
                remark=_clean(row.get("备注")),
                remark2=_clean(row.get("备注2")),
                raw=row,
            )
        )
    return bugs


def make_branch_name(bug: BugRecord) -> str:
    slug = _slugify(bug.description)[:70].strip("-")
    if not slug:
        slug = f"row-{bug.excel_row}"
    return f"fix/bug-{bug.issue_id}-{slug}"


def _clean(value: str | None) -> str:
    return (value or "").strip()


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
