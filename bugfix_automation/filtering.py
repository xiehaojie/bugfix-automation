from __future__ import annotations

from dataclasses import dataclass
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
    assignee: str
    assignee_status: str
    description: str
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
                assignee=_clean(row.get("对接人")),
                assignee_status=_clean(row.get("对接人状态")),
                description=_clean(row.get("问题描述")),
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

