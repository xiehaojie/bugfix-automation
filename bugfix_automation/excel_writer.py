from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import zipfile
import xml.etree.ElementTree as ET

from bugfix_automation.excel_reader import MAIN_NS, NS, _cell_value, _column_index, _read_shared_strings, _sheet_path


ET.register_namespace("", MAIN_NS)


def update_cell_by_header(workbook_path: Path, sheet_name: str, excel_row: int, header: str, value: str) -> None:
    with zipfile.ZipFile(workbook_path) as archive:
        shared_strings = _read_shared_strings(archive)
        sheet_path = _sheet_path(archive, sheet_name)
        sheet_xml = archive.read(sheet_path)

    root = ET.fromstring(sheet_xml)
    column_index = _header_column_index(root, shared_strings, header)
    if column_index is None:
        raise ValueError(f"Excel 中没有找到列：{header}")
    row = _find_or_create_row(root, excel_row)
    cell = _find_or_create_cell(row, column_index, excel_row)
    _set_inline_string(cell, value)
    _replace_zip_entry(workbook_path, sheet_path, ET.tostring(root, encoding="utf-8", xml_declaration=True))


def _header_column_index(root: ET.Element, shared_strings: list[str], header: str) -> int | None:
    first_row = root.find("a:sheetData/a:row[@r='1']", NS)
    if first_row is None:
        return None
    for cell in first_row.findall("a:c", NS):
        if _cell_value(cell, shared_strings) == header:
            return _column_index(cell.attrib.get("r", ""))
    return None


def _find_or_create_row(root: ET.Element, excel_row: int) -> ET.Element:
    sheet_data = root.find("a:sheetData", NS)
    if sheet_data is None:
        sheet_data = ET.SubElement(root, f"{{{MAIN_NS}}}sheetData")
    row = sheet_data.find(f"a:row[@r='{excel_row}']", NS)
    if row is not None:
        return row
    row = ET.Element(f"{{{MAIN_NS}}}row", {"r": str(excel_row)})
    sheet_data.append(row)
    return row


def _find_or_create_cell(row: ET.Element, column_index: int, excel_row: int) -> ET.Element:
    cell_ref = f"{_column_letters(column_index)}{excel_row}"
    for cell in row.findall("a:c", NS):
        if cell.attrib.get("r") == cell_ref:
            return cell
    cell = ET.Element(f"{{{MAIN_NS}}}c", {"r": cell_ref})
    row.append(cell)
    return cell


def _set_inline_string(cell: ET.Element, value: str) -> None:
    cell_ref = cell.attrib.get("r", "")
    style = cell.attrib.get("s")
    cell.clear()
    cell.attrib["r"] = cell_ref
    if style:
        cell.attrib["s"] = style
    cell.attrib["t"] = "inlineStr"
    inline = ET.SubElement(cell, f"{{{MAIN_NS}}}is")
    text = ET.SubElement(inline, f"{{{MAIN_NS}}}t")
    text.text = value


def _replace_zip_entry(workbook_path: Path, entry_name: str, content: bytes) -> None:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        tmp_path = Path(tmp.name)
    try:
        with zipfile.ZipFile(workbook_path, "r") as source, zipfile.ZipFile(tmp_path, "w") as target:
            for item in source.infolist():
                if item.filename == entry_name:
                    target.writestr(item, content)
                else:
                    target.writestr(item, source.read(item.filename))
        shutil.move(str(tmp_path), workbook_path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def _column_letters(index: int) -> str:
    letters = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters
