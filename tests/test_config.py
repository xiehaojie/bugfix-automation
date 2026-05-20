import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from bugfix_automation.config import load_config, update_config_yaml


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
cli_tool: /tmp/codex
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
        self.assertEqual(config.active_workspace, "pc-web")
        self.assertEqual(config.max_concurrency, 2)

    def test_environment_overrides_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text("assignee: 张三\nschedule:\n  hour: 21\n", encoding="utf-8")
            with patch.dict("os.environ", {"BUGFIX_ASSIGNEE": "谢浩杰", "BUGFIX_SCHEDULE_HOUR": "22"}):
                config = load_config(path)

        self.assertEqual(config.assignee, "谢浩杰")
        self.assertEqual(config.schedule_hour, 22)

    def test_update_config_yaml_preserves_file_and_updates_nested_schedule(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text(
                "# demo\nexcel_path: /tmp/old.xlsx\nschedule:\n  hour: 22\n  minute: 0\n",
                encoding="utf-8",
            )

            update_config_yaml({"excel_path": "/tmp/new.xlsx", "schedule": {"hour": 8, "minute": 45}}, path)
            config = load_config(path)

        self.assertEqual(config.excel_path, Path("/tmp/new.xlsx"))
        self.assertEqual(config.schedule_hour, 8)
        self.assertEqual(config.schedule_minute, 45)

    def test_load_config_reads_workspaces_filters_and_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text(
                """
active_workspace: admin
excel_path: /tmp/bugs.xlsx
sheet_name: Sheet1
assignee: 李四
max_concurrency: 3
branch_summary_fields:
  - 问题描述
workspaces:
  - id: admin
    name: 管理后台
    target_repo: /tmp/admin-repo
    target_app_path: apps/admin
    scope_paths: apps/admin,packages/ui
    verify_commands: pnpm lint,pnpm build
    prompt_context_paths: apps/admin/src,packages/ui/src
    max_concurrency: 3
filters:
  - field: 负责人
    op: equals
    value: 李四
  - field: 状态
    op: not_in
    values: 已解决,已处理
prompt:
  fields: 序号,问题描述,备注
  template: 先修前端
  context_paths: apps/admin/src/pages
""",
                encoding="utf-8",
            )

            config = load_config(path)

        self.assertEqual(config.active_workspace, "admin")
        self.assertEqual(config.target_repo, Path("/tmp/admin-repo"))
        self.assertEqual(config.target_app_path, "apps/admin")
        self.assertEqual(config.max_concurrency, 3)
        self.assertEqual(config.workspaces[0].verify_commands, (("pnpm", "lint"), ("pnpm", "build")))
        self.assertEqual(config.filters[0].field, "负责人")
        self.assertEqual(config.filters[1].values, ("已解决", "已处理"))
        self.assertEqual(config.prompt_fields, ("序号", "问题描述", "备注"))
        self.assertIn("apps/admin/src/pages", config.prompt_context_paths)
        self.assertEqual(config.branch_summary_fields, ("问题描述",))


if __name__ == "__main__":
    unittest.main()
