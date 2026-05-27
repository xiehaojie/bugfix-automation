from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
import html
import zipfile

from bugfix_automation.config import Config, repo_root_path
from bugfix_automation.excel.reader import read_sheet
from bugfix_automation.infra.file_metadata import file_metadata
from bugfix_automation.infra.uploads import safe_upload_name, validate_uploaded_xlsx
from bugfix_automation.integrations.online_sheets.base import OnlineSheetProvider, SheetTable
from bugfix_automation.integrations.online_sheets.common import normalize_range_address
from bugfix_automation.integrations.online_sheets.registry import get_provider, provider_options
from bugfix_automation.storage.repositories import save_excel_import
from bugfix_automation.storage.settings import set_setting


DEFAULT_RANGE = "A1:Z1000"


def list_online_sheet_providers() -> dict[str, Any]:
    return {"ok": True, "providers": provider_options()}


def preview_online_sheet(
    config: Config,
    *,
    provider_key: str,
    url: str,
    range_address: str = DEFAULT_RANGE,
    provider: OnlineSheetProvider | None = None,
) -> dict[str, Any]:
    table = _read_online_table(provider_key, url, range_address, provider)
    return {
        "ok": True,
        "provider": table.ref.provider,
        "source_url": table.ref.source_url,
        "workbook_id": table.ref.workbook_id,
        "sheet_id": table.ref.sheet_id,
        "range": table.range_address,
        "headers": table.headers,
        "row_count": len(table.rows),
        "rows": table.rows[:20],
    }


def import_online_sheet(
    config: Config,
    *,
    provider_key: str,
    url: str,
    range_address: str = DEFAULT_RANGE,
    provider: OnlineSheetProvider | None = None,
) -> dict[str, Any]:
    table = _read_online_table(provider_key, url, range_address, provider)
    if not table.headers:
        raise ValueError("在线表格没有读取到表头")

    uploads_root = repo_root_path() / "uploads"
    uploads_root.mkdir(parents=True, exist_ok=True)
    original_name = f"{table.ref.provider}-{table.ref.workbook_id}.xlsx"
    target = uploads_root / safe_upload_name(original_name)
    target.write_bytes(_table_to_xlsx_bytes(table, config.sheet_name))
    validate_uploaded_xlsx(target)

    _save_online_excel_setting(config, table, target)
    rows = read_sheet(target, config.sheet_name)
    _record_online_excel_import(config, table, target, rows)
    return {
        "ok": True,
        "excel_path": str(target),
        "filename": original_name,
        "file": file_metadata(target, original_name=original_name),
        "headers": table.headers,
        "row_count": len(table.rows),
        "online_sheet": _online_sheet_setting(table),
        "config": {"excel_path": str(target)},
    }


def _read_online_table(
    provider_key: str,
    url: str,
    range_address: str,
    provider: OnlineSheetProvider | None,
) -> SheetTable:
    selected = provider or get_provider(provider_key)
    source_url = url.strip()
    if not source_url:
        raise ValueError("请输入在线表格链接")
    normalized_range = normalize_range_address(range_address.strip() or DEFAULT_RANGE)
    ref = selected.parse_url(source_url)
    return selected.read_range(ref, normalized_range)


def _save_online_excel_setting(config: Config, table: SheetTable, path: Path) -> None:
    set_setting(
        config.storage_db_path,
        "excel",
        {
            "excel_path": str(path),
            "sheet_name": config.sheet_name,
            "online_sheet": _online_sheet_setting(table),
        },
    )


def _online_sheet_setting(table: SheetTable) -> dict[str, str]:
    return {
        "provider": table.ref.provider,
        "source_url": table.ref.source_url,
        "workbook_id": table.ref.workbook_id,
        "sheet_id": table.ref.sheet_id,
        "range": table.range_address,
    }


def _record_online_excel_import(config: Config, table: SheetTable, path: Path, rows: list[dict[str, Any]]) -> None:
    save_excel_import(
        config.storage_db_path,
        original_filename=f"{table.ref.provider}-{table.ref.workbook_id}.xlsx",
        stored_path=path,
        sheet_name=config.sheet_name,
        rows=rows,
        config_snapshot_id=None,
        mapping=config.excel_profile.canonical_fields,
    )


def _table_to_xlsx_bytes(table: SheetTable, sheet_name: str) -> bytes:
    import io

    output = io.BytesIO()
    rows = [table.headers, *[[row.get(header, "") for header in table.headers] for row in table.rows]]
    strings: list[str] = []
    string_index: dict[str, int] = {}

    def shared(value: str) -> int:
        text = str(value)
        if text not in string_index:
            string_index[text] = len(strings)
            strings.append(text)
        return string_index[text]

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _content_types_xml())
        archive.writestr("_rels/.rels", _root_rels_xml())
        archive.writestr("xl/workbook.xml", _workbook_xml(sheet_name))
        archive.writestr("xl/_rels/workbook.xml.rels", _workbook_rels_xml())
        archive.writestr("xl/worksheets/sheet1.xml", _sheet_xml(rows, shared))
        archive.writestr("xl/sharedStrings.xml", _shared_strings_xml(strings))
        archive.writestr("docProps/core.xml", _core_xml())
    return output.getvalue()


def _content_types_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>"""


def _root_rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
</Relationships>"""


def _workbook_xml(sheet_name: str) -> str:
    safe_name = html.escape(sheet_name[:31] or "Sheet1")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="{safe_name}" sheetId="1" r:id="rId1"/></sheets>
</workbook>"""


def _workbook_rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>
</Relationships>"""


def _sheet_xml(rows: list[list[str]], shared: Any) -> str:
    row_xml: list[str] = []
    for row_number, row in enumerate(rows, start=1):
        cells = []
        for col_number, value in enumerate(row, start=1):
            cell_ref = f"{_column_letters(col_number)}{row_number}"
            cells.append(f'<c r="{cell_ref}" t="s"><v>{shared(value)}</v></c>')
        row_xml.append(f'<row r="{row_number}">{"".join(cells)}</row>')
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>{"".join(row_xml)}</sheetData>
</worksheet>"""


def _shared_strings_xml(strings: list[str]) -> str:
    items = "".join(f"<si><t>{html.escape(value)}</t></si>" for value in strings)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="{len(strings)}" uniqueCount="{len(strings)}">{items}</sst>"""


def _core_xml() -> str:
    created = datetime.now().isoformat(timespec="seconds")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/">
  <dc:creator>bugfix-automation</dc:creator>
  <dcterms:created>{created}</dcterms:created>
</cp:coreProperties>"""


def _column_letters(index: int) -> str:
    letters = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters
