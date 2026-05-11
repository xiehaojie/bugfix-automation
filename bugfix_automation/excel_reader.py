from __future__ import annotations

from pathlib import Path
import re
import zipfile
import xml.etree.ElementTree as ET


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"a": MAIN_NS, "r": REL_NS}


def read_sheet(path: Path, sheet_name: str) -> list[dict[str, str]]:
    with zipfile.ZipFile(path) as archive:
        shared_strings = _read_shared_strings(archive)
        sheet_path = _sheet_path(archive, sheet_name)
        root = ET.fromstring(archive.read(sheet_path))

    rows = []
    for row in root.findall("a:sheetData/a:row", NS):
        row_number = int(row.attrib.get("r", "0") or "0")
        values: dict[int, str] = {}
        for cell in row.findall("a:c", NS):
            index = _column_index(cell.attrib.get("r", ""))
            values[index] = _cell_value(cell, shared_strings)
        rows.append((row_number, values))

    if not rows:
        return []

    headers = rows[0][1]
    output: list[dict[str, str]] = []
    for row_number, values in rows[1:]:
        mapped: dict[str, str] = {"_excel_row": str(row_number)}
        for index, header in headers.items():
            if header:
                mapped[header] = values.get(index, "")
        if any(value for key, value in mapped.items() if key != "_excel_row"):
            output.append(mapped)
    return output


def _read_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    strings: list[str] = []
    for item in root.findall("a:si", NS):
        strings.append("".join(text.text or "" for text in item.findall(".//a:t", NS)))
    return strings


def _sheet_path(archive: zipfile.ZipFile, sheet_name: str) -> str:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    relationship_id = None
    for sheet in workbook.findall("a:sheets/a:sheet", NS):
        if sheet.attrib.get("name") == sheet_name:
            relationship_id = sheet.attrib.get(f"{{{REL_NS}}}id")
            break
    if relationship_id is None:
        raise ValueError(f"Worksheet not found: {sheet_name}")

    rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    for rel in rels.findall(f"{{{PKG_REL_NS}}}Relationship"):
        if rel.attrib.get("Id") == relationship_id:
            target = rel.attrib["Target"].lstrip("/")
            return target if target.startswith("xl/") else f"xl/{target}"
    raise ValueError(f"Worksheet relationship not found: {relationship_id}")


def _cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    value = cell.find("a:v", NS)
    if value is None or value.text is None:
        return ""
    raw = value.text
    if cell.attrib.get("t") == "s":
        index = int(raw)
        return shared_strings[index] if index < len(shared_strings) else ""
    return raw


def _column_index(cell_ref: str) -> int:
    letters = re.sub(r"[^A-Z]", "", cell_ref.upper())
    index = 0
    for letter in letters:
        index = index * 26 + (ord(letter) - ord("A") + 1)
    return index

