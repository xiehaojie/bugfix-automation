import tempfile
import unittest
from pathlib import Path
import subprocess

from bugfix_automation.approval import approve_fix, count_pending, diff_to_html, parse_worktree_list
from bugfix_automation.approval_api import _bug_payload
from bugfix_automation.config import Config


class ApprovalTest(unittest.TestCase):
    def test_parse_worktree_list_finds_fix_branches(self) -> None:
        output = """worktree /repo
HEAD abc
branch refs/heads/main

worktree /tmp/fix-one
HEAD def
branch refs/heads/fix/1-个人空间上传反馈

worktree /tmp/other
HEAD ghi
branch refs/heads/feature/demo
"""

        fixes = parse_worktree_list(output)

        self.assertEqual(len(fixes), 1)
        self.assertEqual(fixes[0].branch, "fix/1-个人空间上传反馈")
        self.assertEqual(fixes[0].path, Path("/tmp/fix-one"))

    def test_count_pending_counts_app_changes_only(self) -> None:
        fixes = [
            {"branch": "fix/1-a", "changed_files": ["apps/pc-web/a.tsx"]},
            {"branch": "fix/2-b", "changed_files": []},
            {"branch": "fix/3-c", "changed_files": ["apps/api/a.ts"]},
        ]

        self.assertEqual(count_pending(fixes), 1)

    def test_diff_to_html_marks_added_and_removed_lines(self) -> None:
        html = diff_to_html("""diff --git a/a b/a
--- a/a
+++ b/a
@@ -1 +1 @@
-old
+new
""")

        self.assertIn("diff-line-del", html)
        self.assertIn("diff-line-add", html)
        self.assertIn("old", html)
        self.assertIn("new", html)

    def test_approve_fix_commits_and_removes_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            worktree = root / "worktrees" / "fix-1-demo"
            repo.mkdir()
            subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
            app_file = repo / "apps" / "pc-web" / "a.txt"
            app_file.parent.mkdir(parents=True)
            app_file.write_text("old\n", encoding="utf-8")
            subprocess.run(["git", "add", "apps/pc-web/a.txt"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["git", "worktree", "add", str(worktree), "-b", "fix/1-demo"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
            (worktree / "apps" / "pc-web" / "a.txt").write_text("new\n", encoding="utf-8")
            config = Config(
                excel_path=root / "bugs.xlsx",
                sheet_name="Sheet1",
                assignee="谢浩杰",
                target_repo=repo,
                target_app_path="apps/pc-web",
                worktree_root=root / "worktrees",
                runs_root=root / "runs",
                logs_root=root / "logs",
                launchd_label="local.test",
                codex_bin="codex",
                schedule_hour=22,
                schedule_minute=0,
                approval_web_port=8765,
                approval_api_port=8766,
            )

            with unittest.mock.patch("bugfix_automation.approval.mark_excel_processed", return_value=True):
                commit = approve_fix(config, "fix/1-demo")

            self.assertEqual(len(commit), 40)
            self.assertFalse(worktree.exists())
            branch_check = subprocess.run(["git", "rev-parse", "--verify", "fix/1-demo"], cwd=repo, capture_output=True)
            self.assertEqual(branch_check.returncode, 0)

    def test_bug_payload_contains_filtered_excel_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = Config(
                excel_path=root / "bugs.xlsx",
                sheet_name="Sheet1",
                assignee="谢浩杰",
                target_repo=root / "repo",
                target_app_path="apps/pc-web",
                worktree_root=root / "worktrees",
                runs_root=root / "runs",
                logs_root=root / "logs",
                launchd_label="local.test",
                codex_bin="codex",
                schedule_hour=22,
                schedule_minute=0,
                approval_web_port=8765,
                approval_api_port=8766,
            )
            rows = [
                {"_excel_row": "46", "序号": "1", "提出人状态": "待处理", "来源系统": "小亦PC", "对接人": "谢浩杰", "对接人状态": "处理中", "一级分类": "个人空间", "二级分类": "上传", "问题描述": "上传反馈不明显", "备注": "补充备注"},
                {"_excel_row": "47", "序号": "2", "提出人状态": "待处理", "来源系统": "后台", "对接人": "谢浩杰", "对接人状态": "处理中", "问题描述": "跳过"},
                {"_excel_row": "48", "序号": "3", "提出人状态": "待处理", "来源系统": "小亦PC", "对接人": "谢浩杰", "对接人状态": "已处理", "问题描述": "已经完成的不再显示"},
            ]
            with unittest.mock.patch("bugfix_automation.runner.read_sheet", return_value=rows):
                image_path = root / "runs" / "approval-images" / "fix-1-demo" / "row-46-image-1.png"
                with unittest.mock.patch("bugfix_automation.approval_api.export_bug_images", return_value=[image_path]):
                    bugs = _bug_payload(config)

        self.assertEqual(len(bugs), 1)
        self.assertEqual(bugs[0]["issue_id"], "1")
        self.assertEqual(bugs[0]["excel_row"], 46)
        self.assertEqual(bugs[0]["primary_category"], "个人空间")
        self.assertEqual(bugs[0]["remark"], "补充备注")
        self.assertEqual(bugs[0]["branch"], "fix/1-上传反馈不明显")
        self.assertEqual(bugs[0]["images"][0]["path"], str(image_path))
        self.assertIn("/api/image?path=", bugs[0]["images"][0]["url"])


if __name__ == "__main__":
    unittest.main()
