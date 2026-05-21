import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from bugfix_automation.application.config_service import update_automation_config, update_filters
from bugfix_automation.application.scheduler_service import install
from bugfix_automation.config import Config, load_config, repo_root_path, update_config_yaml
from bugfix_automation.storage.settings import get_setting, set_setting


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

    def test_load_config_does_not_create_missing_sqlite_database(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "config.yaml"
            db_path = root / "data" / "missing.sqlite3"
            config_path.write_text(f"storage_db_path: {db_path}\n", encoding="utf-8")

            self.assertFalse(db_path.exists())
            config = load_config(config_path)

        self.assertEqual(config.storage_db_path, db_path)
        self.assertFalse(db_path.exists())

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

    def test_load_config_prefers_yaml_excel_profile_prompt_over_top_level_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text(
                """
branch_summary_fields:
  - 顶层摘要
prompt:
  fields:
    - 顶层字段
  template: top-level template
excel_profile:
  prompt:
    fields:
      - 画像字段
      - 画像详情
    template: profile template
    branch_summary_fields:
      - 画像摘要
""",
                encoding="utf-8",
            )

            config = load_config(path)

        self.assertEqual(config.prompt_fields, ("画像字段", "画像详情"))
        self.assertEqual(config.prompt_template, "profile template")
        self.assertEqual(config.branch_summary_fields, ("画像摘要",))

    def test_load_config_respects_empty_excel_profile_prompt_values_from_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text(
                """
branch_summary_fields:
  - 顶层摘要
prompt:
  fields:
    - 顶层字段
  template: top-level template
excel_profile:
  prompt:
    fields: []
    template: ""
    branch_summary_fields: []
""",
                encoding="utf-8",
            )

            config = load_config(path)

        self.assertEqual(config.prompt_fields, ())
        self.assertEqual(config.prompt_template, "")
        self.assertEqual(config.branch_summary_fields, ())

    def test_load_config_respects_bare_empty_excel_profile_prompt_template_from_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text(
                """
prompt:
  template: top-level
excel_profile:
  prompt:
    template:
""",
                encoding="utf-8",
            )

            config = load_config(path)

        self.assertEqual(config.prompt_template, "")

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

    def test_minimal_yaml_can_bootstrap_runtime_settings_from_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "config.yaml"
            db_path = root / "data" / "app.sqlite3"
            config_path.write_text(
                f"""
data_root: {root / "data"}
storage_db_path: {db_path}
cli_tool: codex
approval_web_port: 8765
approval_api_port: 8766
""",
                encoding="utf-8",
            )
            set_setting(db_path, "excel", {"excel_path": "/tmp/runtime.xlsx", "sheet_name": "RuntimeSheet"})
            set_setting(
                db_path,
                "automation",
                {
                    "cli_tool": "claude",
                    "max_concurrency": 3,
                    "schedule": {"hour": 8, "minute": 45},
                    "approval_web_port": 9001,
                    "approval_api_port": 9002,
                },
            )
            set_setting(db_path, "active_workspace", "admin")
            set_setting(
                db_path,
                "workspaces",
                [
                    {
                        "id": "admin",
                        "name": "Admin",
                        "target_repo": "/tmp/admin-repo",
                        "repo_paths": ["/tmp/admin-repo"],
                        "target_app_path": "apps/admin",
                        "scope_paths": ["apps/admin"],
                        "verify_commands": ["pnpm lint"],
                        "prompt_context_paths": ["apps/admin/src"],
                        "max_concurrency": 3,
                        "scope": "frontend",
                    }
                ],
            )
            set_setting(db_path, "filters", [{"field": "负责人", "op": "equals", "value": "谢浩杰"}])
            set_setting(db_path, "branch_summary_fields", ["标题"])
            set_setting(db_path, "prompt", {"fields": ["标题", "详情"], "template": "runtime prompt", "context_paths": []})

            config = load_config(config_path)

        self.assertEqual(config.excel_path, Path("/tmp/runtime.xlsx"))
        self.assertEqual(config.sheet_name, "RuntimeSheet")
        self.assertEqual(config.cli_tool, "claude")
        self.assertEqual(config.max_concurrency, 3)
        self.assertEqual(config.schedule_hour, 8)
        self.assertEqual(config.schedule_minute, 45)
        self.assertEqual(config.approval_web_port, 9001)
        self.assertEqual(config.approval_api_port, 9002)
        self.assertEqual(config.active_workspace, "admin")
        self.assertEqual(config.target_repo, Path("/tmp/admin-repo"))
        self.assertEqual(config.target_app_path, "apps/admin")
        self.assertEqual(config.filters[0].value, "谢浩杰")
        self.assertEqual(config.branch_summary_fields, ("标题",))
        self.assertEqual(config.prompt_fields, ("标题", "详情"))
        self.assertEqual(config.prompt_template, "runtime prompt")

    def test_update_filters_writes_sqlite_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "app.sqlite3"
            with patch.dict("os.environ", {"BUGFIX_STORAGE_DB_PATH": str(db_path)}):
                update_filters([{"field": "负责人", "op": "equals", "value": "谢浩杰"}])
            self.assertEqual(get_setting(db_path, "filters"), [{"field": "负责人", "op": "equals", "value": "谢浩杰"}])

    def test_update_automation_config_writes_mutable_sqlite_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "app.sqlite3"
            payload = {
                "max_concurrency": 4,
                "cli_tool": "codex",
                "branch_summary_fields": ["问题描述"],
                "prompt": {"fields": ["序号"], "template": "fix it", "context_paths": []},
            }
            with patch.dict("os.environ", {"BUGFIX_STORAGE_DB_PATH": str(db_path)}):
                update_automation_config(payload)
            self.assertEqual(get_setting(db_path, "automation"), {"cli_tool": "codex", "max_concurrency": 4})
            self.assertEqual(get_setting(db_path, "branch_summary_fields"), ["问题描述"])
            self.assertEqual(get_setting(db_path, "prompt"), {"fields": ["序号"], "template": "fix it", "context_paths": []})

    def test_update_automation_config_syncs_manual_prompt_to_excel_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "app.sqlite3"
            set_setting(
                db_path,
                "excel_profile",
                {
                    "canonical_fields": {"issue_id": "编号", "description": "标题"},
                    "prompt": {
                        "fields": ["旧字段"],
                        "template": "old template",
                        "branch_summary_fields": ["旧摘要"],
                    },
                },
            )

            with patch.dict("os.environ", {"BUGFIX_STORAGE_DB_PATH": str(db_path)}):
                update_automation_config(
                    {
                        "branch_summary_fields": ["新摘要"],
                        "prompt": {"fields": ["新字段"], "template": "new template", "context_paths": ["apps/demo"]},
                    }
                )
                config = load_config()

            profile = get_setting(db_path, "excel_profile")
            self.assertEqual(config.prompt_fields, ("新字段",))
            self.assertEqual(config.prompt_template, "new template")
            self.assertEqual(config.branch_summary_fields, ("新摘要",))
            self.assertEqual(profile["canonical_fields"], {"issue_id": "编号", "description": "标题"})
            self.assertEqual(
                profile["prompt"],
                {
                    "fields": ["新字段"],
                    "template": "new template",
                    "context_paths": ["apps/demo"],
                    "branch_summary_fields": ["新摘要"],
                },
            )
            self.assertEqual(get_setting(db_path, "prompt"), {"fields": ["新字段"], "template": "new template", "context_paths": ["apps/demo"]})
            self.assertEqual(get_setting(db_path, "branch_summary_fields"), ["新摘要"])

    def test_scheduler_install_merges_schedule_into_automation_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "data" / "app.sqlite3"
            config = Config(
                excel_path=root / "bugs.xlsx",
                sheet_name="Sheet1",
                assignee="谢浩杰",
                target_repo=root / "repo",
                target_app_path="apps/pc-web",
                worktree_root=root / "worktrees",
                runs_root=root / "runs",
                logs_root=root / "logs",
                data_root=root / "data",
                storage_db_path=db_path,
                launchd_label="local.test",
                cli_tool="codex",
                schedule_hour=22,
                schedule_minute=0,
                approval_web_port=8765,
                approval_api_port=8766,
            )
            set_setting(db_path, "automation", {"max_concurrency": 3, "cli_tool": "codex"})
            with patch.dict("os.environ", {"BUGFIX_STORAGE_DB_PATH": str(db_path)}):
                with patch("bugfix_automation.application.scheduler_service.install_launchd_at", return_value=root / "launchd.plist"):
                    with patch("bugfix_automation.application.scheduler_service.launchd_status", return_value={}):
                        install(config, 8, 45)
            self.assertEqual(
                get_setting(db_path, "automation"),
                {"cli_tool": "codex", "max_concurrency": 3, "schedule": {"hour": 8, "minute": 45}},
            )

    def test_load_config_reads_excel_profile_from_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "config.yaml"
            db_path = root / "data" / "app.sqlite3"
            config_path.write_text(
                f"""
storage_db_path: {db_path}
branch_summary_fields:
  - yaml summary
prompt:
  fields:
    - yaml field
  template: yaml template
""",
                encoding="utf-8",
            )
            set_setting(db_path, "prompt", {"fields": ["db field"], "template": "db template"})
            set_setting(
                db_path,
                "excel_profile",
                {
                    "canonical_fields": {
                        "issue_id": "编号",
                        "source_system": "系统",
                        "priority": "等级",
                        "primary_category": "一级",
                        "secondary_category": "二级",
                        "requester": "提出者",
                        "request_date": "日期",
                        "requester_status": "提出状态",
                        "assignee": "负责人",
                        "assignee_status": "处理状态",
                        "resolved_date": "完成日期",
                        "description": "标题",
                        "remark": "详情",
                        "remark2": "补充",
                    },
                    "prompt": {
                        "fields": ["标题", "详情"],
                        "template": "adapter template",
                        "branch_summary_fields": ["标题"],
                    },
                },
            )

            config = load_config(config_path)

        self.assertEqual(config.excel_profile.canonical_fields.issue_id, "编号")
        self.assertEqual(config.excel_profile.canonical_fields.source_system, "系统")
        self.assertEqual(config.excel_profile.canonical_fields.priority, "等级")
        self.assertEqual(config.excel_profile.canonical_fields.primary_category, "一级")
        self.assertEqual(config.excel_profile.canonical_fields.secondary_category, "二级")
        self.assertEqual(config.excel_profile.canonical_fields.requester, "提出者")
        self.assertEqual(config.excel_profile.canonical_fields.request_date, "日期")
        self.assertEqual(config.excel_profile.canonical_fields.requester_status, "提出状态")
        self.assertEqual(config.excel_profile.canonical_fields.assignee, "负责人")
        self.assertEqual(config.excel_profile.canonical_fields.assignee_status, "处理状态")
        self.assertEqual(config.excel_profile.canonical_fields.resolved_date, "完成日期")
        self.assertEqual(config.excel_profile.canonical_fields.description, "标题")
        self.assertEqual(config.excel_profile.canonical_fields.remark, "详情")
        self.assertEqual(config.excel_profile.canonical_fields.remark2, "补充")
        self.assertEqual(config.prompt_fields, ("标题", "详情"))
        self.assertEqual(config.prompt_template, "adapter template")
        self.assertEqual(config.branch_summary_fields, ("标题",))

    def test_load_config_respects_empty_excel_profile_prompt_values_from_sqlite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "config.yaml"
            db_path = root / "data" / "app.sqlite3"
            config_path.write_text(
                f"""
storage_db_path: {db_path}
branch_summary_fields:
  - yaml summary
prompt:
  fields:
    - yaml field
  template: yaml template
""",
                encoding="utf-8",
            )
            set_setting(
                db_path,
                "excel_profile",
                {
                    "prompt": {
                        "fields": [],
                        "template": "",
                        "branch_summary_fields": [],
                    }
                },
            )

            config = load_config(config_path)

        self.assertEqual(config.prompt_fields, ())
        self.assertEqual(config.prompt_template, "")
        self.assertEqual(config.branch_summary_fields, ())

    def test_load_config_prefers_empty_sqlite_excel_profile_context_paths_over_top_level_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "config.yaml"
            db_path = root / "data" / "app.sqlite3"
            config_path.write_text(
                f"""
storage_db_path: {db_path}
prompt:
  context_paths:
    - yaml-top-level
""",
                encoding="utf-8",
            )
            set_setting(db_path, "prompt", {"context_paths": ["sqlite-top-level"]})
            set_setting(db_path, "excel_profile", {"prompt": {"context_paths": []}})

            config = load_config(config_path)

        self.assertEqual(config.prompt_context_paths, ())

    def test_load_config_prefers_sqlite_excel_profile_context_paths_over_top_level_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "config.yaml"
            db_path = root / "data" / "app.sqlite3"
            config_path.write_text(
                f"""
storage_db_path: {db_path}
prompt:
  context_paths:
    - yaml-top-level
""",
                encoding="utf-8",
            )
            set_setting(db_path, "prompt", {"context_paths": ["sqlite-top-level"]})
            set_setting(db_path, "excel_profile", {"prompt": {"context_paths": ["profile-path"]}})

            config = load_config(config_path)

        self.assertEqual(config.prompt_context_paths, ("profile-path",))

    def test_load_config_uses_yaml_when_sqlite_settings_cannot_be_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "config.yaml"
            db_path = root / "data" / "app.sqlite3"
            db_path.parent.mkdir(parents=True)
            db_path.write_text("not a sqlite database", encoding="utf-8")
            config_path.write_text(
                f"""
storage_db_path: {db_path}
excel_path: /tmp/from-yaml.xlsx
sheet_name: SheetFromYaml
max_concurrency: 3
prompt:
  fields: 问题描述
  template: yaml template
""",
                encoding="utf-8",
            )

            config = load_config(config_path)

        self.assertEqual(config.excel_path, Path("/tmp/from-yaml.xlsx"))
        self.assertEqual(config.sheet_name, "SheetFromYaml")
        self.assertEqual(config.max_concurrency, 3)
        self.assertEqual(config.prompt_fields, ("问题描述",))
        self.assertEqual(config.prompt_template, "yaml template")


if __name__ == "__main__":
    unittest.main()
