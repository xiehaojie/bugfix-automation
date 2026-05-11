import tempfile
import unittest
from pathlib import Path

from bugfix_automation.approval import count_pending, diff_to_html, parse_worktree_list


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


if __name__ == "__main__":
    unittest.main()
