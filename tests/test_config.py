import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from bugfix_automation.config import load_config, repo_root_path, update_config_yaml
from bugfix_automation.storage.settings import set_setting


class ConfigTest(unittest.TestCase):
    def test_default_worktree_root_stays_inside_automation_repo(self) -> None:
        config = load_config()

        self.assertIn("bugfix-automation", str(config.worktree_root))
        self.assertNotIn("/code/monorepo/.worktrees", str(config.worktree_root))

    def test_storage_paths_default_to_repo_data_dir(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            config = load_config()

        self.assertEqual(config.data_root, repo_root_path() / "data")
        self.assertEqual(config.storage_db_path, repo_root_path() / "data" / "app.sqlite3")

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
        self.assertIn("bugfix-automation", str(config.worktree_root))
        self.assertEqual(config.worktree_root.name, ".target-worktrees")
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

    def test_load_config_merges_sqlite_settings_over_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "config.yaml"
            db_path = root / "data" / "app.sqlite3"
            config_path.write_text(
                f"""
storage_db_path: {db_path}
excel_path: /tmp/from-yaml.xlsx
sheet_name: SheetFromYaml
max_concurrency: 1
prompt:
  fields: 问题描述
  template: yaml template
""",
                encoding="utf-8",
            )
            set_setting(db_path, "excel", {"excel_path": "/tmp/from-sqlite.xlsx", "sheet_name": "SheetFromDb"})
            set_setting(db_path, "automation", {"max_concurrency": 4})
            set_setting(
                db_path,
                "prompt",
                {"fields": ["标题", "详情"], "template": "db template", "context_paths": []},
            )

            config = load_config(config_path)

        self.assertEqual(config.excel_path, Path("/tmp/from-sqlite.xlsx"))
        self.assertEqual(config.sheet_name, "SheetFromDb")
        self.assertEqual(config.max_concurrency, 4)
        self.assertEqual(config.prompt_fields, ("标题", "详情"))
        self.assertEqual(config.prompt_template, "db template")

    def test_load_config_reads_excel_profile_from_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "config.yaml"
            db_path = root / "data" / "app.sqlite3"
            config_path.write_text(f"storage_db_path: {db_path}\n", encoding="utf-8")
            set_setting(
                db_path,
                "excel_profile",
                {
                    "canonical_fields": {"issue_id": "编号", "description": "标题", "assignee": "负责人"},
                    "prompt": {
                        "fields": ["标题", "详情"],
                        "template": "adapter template",
                        "branch_summary_fields": ["标题"],
                    },
                },
            )

            config = load_config(config_path)

        self.assertEqual(config.excel_profile.canonical_fields.issue_id, "编号")
        self.assertEqual(config.excel_profile.canonical_fields.description, "标题")
        self.assertEqual(config.prompt_fields, ("标题", "详情"))
        self.assertEqual(config.prompt_template, "adapter template")
        self.assertEqual(config.branch_summary_fields, ("标题",))


if __name__ == "__main__":
    unittest.main()
