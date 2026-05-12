import tempfile
import unittest
import zipfile
from pathlib import Path

from bugfix_automation.excel_reader import read_sheet
from bugfix_automation.excel_writer import update_cell_by_header


def write_minimal_xlsx(path: Path) -> None:
    files = {
        "[Content_Types].xml": """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>
</Types>""",
        "_rels/.rels": """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>""",
        "xl/workbook.xml": """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="在线问题清单" sheetId="1" r:id="rId1"/></sheets>
</workbook>""",
        "xl/_rels/workbook.xml.rels": """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>""",
        "xl/sharedStrings.xml": """<?xml version="1.0" encoding="UTF-8"?>
<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="6" uniqueCount="6">
  <si><t>序号</t></si><si><t>提出人状态</t></si><si><t>来源系统</t></si>
  <si><t>对接人</t></si><si><t>对接人状态</t></si><si><t>问题描述</t></si>
  <si><t>处理中</t></si><si><t>小亦PC</t></si><si><t>谢浩杰</t></si><si><t>账号离线状态</t></si>
</sst>""",
        "xl/worksheets/sheet1.xml": """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1">
      <c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c><c r="C1" t="s"><v>2</v></c>
      <c r="D1" t="s"><v>3</v></c><c r="E1" t="s"><v>4</v></c><c r="F1" t="s"><v>5</v></c>
    </row>
    <row r="2">
      <c r="A2"><v>87</v></c><c r="B2" t="s"><v>6</v></c><c r="C2" t="s"><v>7</v></c>
      <c r="D2" t="s"><v>8</v></c><c r="F2" t="s"><v>9</v></c>
    </row>
  </sheetData>
</worksheet>""",
    }
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)


class ExcelReaderTest(unittest.TestCase):
    def test_read_sheet_maps_rows_by_header(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workbook = Path(tmp) / "bugs.xlsx"
            write_minimal_xlsx(workbook)

            rows = read_sheet(workbook, "在线问题清单")

        self.assertEqual(rows[0]["序号"], "87")
        self.assertEqual(rows[0]["提出人状态"], "处理中")
        self.assertEqual(rows[0]["来源系统"], "小亦PC")
        self.assertEqual(rows[0]["对接人"], "谢浩杰")
        self.assertEqual(rows[0]["对接人状态"], "")
        self.assertEqual(rows[0]["问题描述"], "账号离线状态")

    def test_read_sheet_skips_rows_hidden_by_excel_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workbook = Path(tmp) / "bugs.xlsx"
            write_minimal_xlsx(workbook)
            with zipfile.ZipFile(workbook, "a") as archive:
                archive.writestr(
                    "xl/worksheets/sheet1.xml",
                    """<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>
    <row r="1">
      <c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c><c r="C1" t="s"><v>2</v></c>
      <c r="D1" t="s"><v>3</v></c><c r="E1" t="s"><v>4</v></c><c r="F1" t="s"><v>5</v></c>
    </row>
    <row r="2" hidden="1">
      <c r="A2"><v>87</v></c><c r="B2" t="s"><v>6</v></c><c r="C2" t="s"><v>7</v></c>
      <c r="D2" t="s"><v>8</v></c><c r="F2" t="s"><v>9</v></c>
    </row>
    <row r="9">
      <c r="A9"><v>88</v></c><c r="B9" t="s"><v>6</v></c><c r="C9" t="s"><v>7</v></c>
      <c r="D9" t="s"><v>8</v></c><c r="F9" t="s"><v>9</v></c>
    </row>
  </sheetData>
</worksheet>""",
                )

            rows = read_sheet(workbook, "在线问题清单")

        self.assertEqual([row["序号"] for row in rows], ["88"])
        self.assertEqual(rows[0]["_excel_row"], "9")

    def test_update_cell_by_header_writes_inline_status_without_rebuilding_workbook(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workbook = Path(tmp) / "bugs.xlsx"
            write_minimal_xlsx(workbook)

            update_cell_by_header(workbook, "在线问题清单", 2, "对接人状态", "已处理")
            rows = read_sheet(workbook, "在线问题清单")

        self.assertEqual(rows[0]["对接人状态"], "已处理")


if __name__ == "__main__":
    unittest.main()
