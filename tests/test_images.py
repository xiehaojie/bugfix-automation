import tempfile
import unittest
import zipfile
from pathlib import Path

from bugfix_automation.filtering import filter_bugs
from bugfix_automation.images import export_bug_images, image_ids_from_row, image_map
from bugfix_automation.runner import codex_command


def write_image_xlsx(path: Path) -> None:
    files = {
        "xl/cellimages.xml": """<?xml version="1.0" encoding="UTF-8"?>
<etc:cellImages xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:etc="http://www.wps.cn/officeDocument/2017/etCustomData">
  <etc:cellImage><xdr:pic><xdr:nvPicPr><xdr:cNvPr id="1" name="ID_SCREENSHOT_ONE"/></xdr:nvPicPr><xdr:blipFill><a:blip r:embed="rId1"/></xdr:blipFill></xdr:pic></etc:cellImage>
</etc:cellImages>""",
        "xl/_rels/cellimages.xml.rels": """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image1.png"/>
</Relationships>""",
        "xl/media/image1.png": b"fake-png",
    }
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)


class ImagesTest(unittest.TestCase):
    def test_image_ids_from_row_reads_screenshot_columns(self) -> None:
        row = {"截图1": '=DISPIMG("ID_SCREENSHOT_ONE",1)', "截图2": "", "截图3": '=DISPIMG("ID_SCREENSHOT_TWO",1)'}

        self.assertEqual(image_ids_from_row(row), ["ID_SCREENSHOT_ONE", "ID_SCREENSHOT_TWO"])

    def test_image_map_reads_wps_cellimages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workbook = Path(tmp) / "bugs.xlsx"
            write_image_xlsx(workbook)

            mapping = image_map(workbook)

        self.assertEqual(mapping["ID_SCREENSHOT_ONE"], "xl/media/image1.png")

    def test_export_bug_images_writes_row_images(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workbook = Path(tmp) / "bugs.xlsx"
            write_image_xlsx(workbook)
            bug = filter_bugs([
                {
                    "_excel_row": "2",
                    "序号": "87",
                    "提出人状态": "处理中",
                    "来源系统": "小亦PC",
                    "对接人": "谢浩杰",
                    "对接人状态": "",
                    "问题描述": "账号离线",
                    "截图1": '=DISPIMG("ID_SCREENSHOT_ONE",1)',
                }
            ], assignee="谢浩杰")[0]

            paths = export_bug_images(workbook, bug, Path(tmp) / "out")

            self.assertEqual(len(paths), 1)
            self.assertEqual(paths[0].read_bytes(), b"fake-png")
            self.assertEqual(paths[0].suffix, ".png")

    def test_codex_command_includes_image_arguments(self) -> None:
        command = codex_command("/usr/local/bin/codex", "/tmp/worktree", "prompt", [Path("/tmp/one.png"), Path("/tmp/two.jpg")])

        self.assertIn("--image", command)
        self.assertIn("/tmp/one.png", command)
        self.assertIn("/tmp/two.jpg", command)
        self.assertEqual(command[-1], "-")


if __name__ == "__main__":
    unittest.main()
