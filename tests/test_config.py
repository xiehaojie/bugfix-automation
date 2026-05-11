import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from bugfix_automation.config import load_config


class ConfigTest(unittest.TestCase):
    def test_default_worktree_root_stays_inside_automation_repo(self) -> None:
        config = load_config()

        self.assertIn("bugfix-automation", str(config.worktree_root))
        self.assertNotIn("/code/monorepo/.worktrees", str(config.worktree_root))

    def test_load_config_reads_yaml_and_resolves_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text(
                """
excel_path: ~/Desktop/demo.xlsx
sheet_name: Sheet1
assignee: 张三
target_repo: /tmp/monorepo
target_app_path: apps/demo
worktree_root: .target-worktrees
runs_root: runs
logs_root: logs
launchd_label: local.demo
codex_bin: /tmp/codex
approval_web_port: 9001
approval_api_port: 9002
excel_processed_status_column: 对接人状态
excel_processed_status_value: 已处理
schedule:
  hour: 21
  minute: 30
""",
                encoding="utf-8",
            )

            config = load_config(path)

        self.assertEqual(config.sheet_name, "Sheet1")
        self.assertEqual(config.assignee, "张三")
        self.assertEqual(config.target_repo, Path("/tmp/monorepo"))
        self.assertEqual(config.target_app_path, "apps/demo")
        self.assertIn("bugfix-automation/.target-worktrees", str(config.worktree_root))
        self.assertEqual(config.schedule_hour, 21)
        self.assertEqual(config.schedule_minute, 30)
        self.assertEqual(config.approval_web_port, 9001)
        self.assertEqual(config.approval_api_port, 9002)
        self.assertEqual(config.excel_processed_status_column, "对接人状态")
        self.assertEqual(config.excel_processed_status_value, "已处理")

    def test_environment_overrides_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text("assignee: 张三\nschedule:\n  hour: 21\n", encoding="utf-8")
            with patch.dict("os.environ", {"BUGFIX_ASSIGNEE": "谢浩杰", "BUGFIX_SCHEDULE_HOUR": "22"}):
                config = load_config(path)

        self.assertEqual(config.assignee, "谢浩杰")
        self.assertEqual(config.schedule_hour, 22)


if __name__ == "__main__":
    unittest.main()
