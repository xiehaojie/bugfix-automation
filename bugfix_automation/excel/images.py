from __future__ import annotations

from pathlib import Path
import re
import zipfile
import xml.etree.ElementTree as ET

from bugfix_automation.domain.filtering import BugRecord


PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
XDR_NS = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS = {"xdr": XDR_NS, "a": A_NS}
SCREENSHOT_COLUMNS = ("截图1", "截图2", "截图3")
DISPIMG_RE = re.compile(r'DISPIMG\("([^"]+)"')


def image_ids_from_row(row: dict[str, str]) -> list[str]:
    ids: list[str] = []
    for column in SCREENSHOT_COLUMNS:
        value = row.get(column, "")
        ids.extend(DISPIMG_RE.findall(value))
    return ids


def image_map(workbook_path: Path) -> dict[str, str]:
    with zipfile.ZipFile(workbook_path) as archive:
        if "xl/cellimages.xml" not in archive.namelist() or "xl/_rels/cellimages.xml.rels" not in archive.namelist():
            return {}
        rels = _cellimage_relationships(archive)
        root = ET.fromstring(archive.read("xl/cellimages.xml"))

    mapping: dict[str, str] = {}
    for pic in root.findall(".//xdr:pic", NS):
        prop = pic.find(".//xdr:cNvPr", NS)
        blip = pic.find(".//a:blip", NS)
        if prop is None or blip is None:
            continue
        image_id = prop.attrib.get("name")
        rel_id = blip.attrib.get(f"{{{REL_NS}}}embed")
        target = rels.get(rel_id or "")
        if image_id and target:
            mapping[image_id] = target
    return mapping


def export_bug_images(workbook_path: Path, bug: BugRecord, output_dir: Path) -> list[Path]:
    ids = image_ids_from_row(bug.raw)
    if not ids:
        return []
    mapping = image_map(workbook_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    exported: list[Path] = []
    with zipfile.ZipFile(workbook_path) as archive:
        for index, image_id in enumerate(ids, start=1):
            source = mapping.get(image_id)
            if source is None or source not in archive.namelist():
                continue
            suffix = Path(source).suffix or ".image"
            target = output_dir / f"row-{bug.excel_row}-image-{index}{suffix}"
            target.write_bytes(archive.read(source))
            exported.append(target)
    return exported


def _cellimage_relationships(archive: zipfile.ZipFile) -> dict[str, str]:
    root = ET.fromstring(archive.read("xl/_rels/cellimages.xml.rels"))
    rels: dict[str, str] = {}
    for rel in root.findall(f"{{{PKG_REL_NS}}}Relationship"):
        target = rel.attrib.get("Target", "").lstrip("/")
        if target and not target.startswith("xl/"):
            target = f"xl/{target}"
        rels[rel.attrib.get("Id", "")] = target
    return rels

