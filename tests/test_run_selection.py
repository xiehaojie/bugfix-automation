import tempfile
import unittest
from pathlib import Path

from bugfix_automation.domain.filtering import filter_bugs
from bugfix_automation.orchestration.bug_runner import select_one_bug, write_bug_results


class RunSelectionTest(unittest.TestCase):
    def setUp(self) -> None:
        rows = [
            {"_excel_row": "46", "序号": "1", "提出人状态": "处理中", "来源系统": "小亦PC", "对接人": "谢浩杰", "对接人状态": "", "问题描述": "上传反馈"},
            {"_excel_row": "87", "序号": "7", "提出人状态": "处理中", "来源系统": "小亦APP", "对接人": "谢浩杰", "对接人状态": "", "问题描述": "离线状态"},
        ]
        self.bugs = filter_bugs(rows, "谢浩杰")

    def test_select_one_bug_by_issue_id(self) -> None:
        bug = select_one_bug(self.bugs, issue_id="7", excel_row=None)

        self.assertEqual(bug.excel_row, 87)
        self.assertEqual(bug.description, "离线状态")

    def test_select_one_bug_by_excel_row(self) -> None:
        bug = select_one_bug(self.bugs, issue_id=None, excel_row=46)

        self.assertEqual(bug.issue_id, "1")

    def test_select_one_bug_requires_exact_match(self) -> None:
        with self.assertRaisesRegex(ValueError, "没有找到匹配项"):
            select_one_bug(self.bugs, issue_id="999", excel_row=None)

    def test_write_bug_results_writes_single_bug_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bug = self.bugs[0]
            json_path, md_path, approval_path = write_bug_results(
                Path(tmp),
                [
                    {
                        "excel_row": bug.excel_row,
                        "issue_id": bug.issue_id,
                        "status": "dry-run",
                        "branch": "fix/bug-1-demo",
                        "detail": "single",
                    }
                ],
            )

            approval = approval_path.read_text(encoding="utf-8")
            self.assertTrue(json_path.exists())
            self.assertTrue(md_path.exists())

        self.assertIn("Bug 1 - Excel 第 46 行", approval)


if __name__ == "__main__":
    unittest.main()
