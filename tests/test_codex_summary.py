import unittest

from bugfix_automation.codex_summary import branch_name_from_summary, sanitize_summary


class CodexSummaryTest(unittest.TestCase):
    def test_branch_name_from_summary_uses_issue_id_and_codex_text(self) -> None:
        branch = branch_name_from_summary("24", "收藏夹列表展示收藏条目 skill")

        self.assertEqual(branch, "fix/24-收藏夹列表展示收藏条目skill")

    def test_sanitize_summary_limits_noise_and_keeps_chinese(self) -> None:
        summary = sanitize_summary("fix(pc-web): 37- 可能会接收到多个重复待办，希望能够帮我！！！")

        self.assertEqual(summary, "可能会接收到多个重复待办希望能够帮我")


if __name__ == "__main__":
    unittest.main()
