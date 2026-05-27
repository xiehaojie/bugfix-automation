from __future__ import annotations

from collections import Counter
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import Any

from bugfix_automation.config import load_config, repo_root_path
from bugfix_automation.excel.reader import read_sheet
from bugfix_automation.infra.file_metadata import file_metadata
from bugfix_automation.infra.uploads import safe_upload_name, validate_uploaded_xlsx, validate_xlsx
from bugfix_automation.storage.repositories import save_excel_import
from bugfix_automation.storage.settings import set_setting


def upload_excel_from_multipart(body: bytes, content_type: str) -> dict[str, Any]:
    if "multipart/form-data" not in content_type:
        raise ValueError("请使用表单上传 xlsx 文件")
    filename, file_bytes = extract_multipart_file(body, content_type)
    return upload_excel_bytes(filename, file_bytes)


def upload_excel_bytes(filename: str, file_bytes: bytes) -> dict[str, Any]:
    if not filename:
        raise ValueError("没有收到文件")
    original_name = Path(filename).name
    if not original_name.lower().endswith(".xlsx"):
        raise ValueError("只支持 .xlsx 文件")
    uploads_root = repo_root_path() / "uploads"
    uploads_root.mkdir(parents=True, exist_ok=True)
    target = uploads_root / safe_upload_name(original_name)
    target.write_bytes(file_bytes)
    validate_uploaded_xlsx(target)
    _save_excel_setting(target)
    _record_excel_import(original_name, target)
    return {
        "ok": True,
        "excel_path": str(target),
        "filename": original_name,
        "file": file_metadata(target, original_name=original_name),
        "config": {"excel_path": str(target)},
    }


def select_excel_path(raw_path: str) -> dict[str, Any]:
    path = Path(raw_path).expanduser().resolve()
    validate_xlsx(path)
    _save_excel_setting(path)
    _record_excel_import(path.name, path)
    return {"ok": True, "excel_path": str(path), "file": file_metadata(path)}


def _save_excel_setting(path: Path) -> None:
    config = load_config()
    set_setting(config.storage_db_path, "excel", {"excel_path": str(path), "sheet_name": config.sheet_name})


def _record_excel_import(original_name: str, path: Path) -> None:
    try:
        config = load_config()
        rows = read_sheet(path, config.sheet_name)
        save_excel_import(
            config.storage_db_path,
            original_filename=original_name,
            stored_path=path,
            sheet_name=config.sheet_name,
            rows=rows,
            config_snapshot_id=None,
            mapping=config.excel_profile.canonical_fields,
        )
    except Exception:
        return


def get_excel_columns(max_distinct: int = 50) -> dict[str, Any]:
    """Read the configured Excel and return headers + distinct values per column.

    Used by the UI to power multi-select pickers for filter rules and prompt fields.
    """
    config = load_config()
    if not config.excel_path.exists():
        return {"ok": False, "error": "未配置 Excel 文件", "headers": [], "columns": {}}
    try:
        rows = read_sheet(config.excel_path, config.sheet_name)
    except Exception as exc:
        return {"ok": False, "error": str(exc), "headers": [], "columns": {}}

    if not rows:
        return {"ok": True, "headers": [], "columns": {}, "row_count": 0}

    headers: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row.keys():
            if key == "_excel_row" or key in seen:
                continue
            seen.add(key)
            headers.append(key)

    columns: dict[str, list[dict[str, Any]]] = {}
    for header in headers:
        counter: Counter[str] = Counter()
        for row in rows:
            val = (row.get(header) or "").strip()
            if val:
                counter[val] += 1
        items = [
            {"value": value, "count": count}
            for value, count in counter.most_common(max_distinct)
        ]
        columns[header] = items
    return {"ok": True, "headers": headers, "columns": columns, "row_count": len(rows)}


def extract_multipart_file(body: bytes, content_type: str) -> tuple[str, bytes]:
    message = BytesParser(policy=policy.default).parsebytes(
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8") + body
    )
    if not message.is_multipart():
        raise ValueError("没有收到文件")
    for part in message.iter_parts():
        if part.get_content_disposition() != "form-data":
            continue
        if part.get_param("name", header="content-disposition") != "file":
            continue
        filename = part.get_filename() or ""
        payload = part.get_payload(decode=True) or b""
        if filename:
            return filename, payload
    raise ValueError("没有收到文件")
