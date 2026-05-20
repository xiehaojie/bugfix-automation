import unittest
import tempfile
from pathlib import Path
import plistlib
from unittest.mock import patch

from bugfix_automation.config import Config
from bugfix_automation.scheduler import install_launchd_at, launchd_status, resolve_cli_tool, uninstall_launchd


class SchedulerTest(unittest.TestCase):
    def test_resolve_cli_tool_fails_without_absolute_path(self) -> None:
        with patch("bugfix_automation.scheduler.shutil.which", return_value=None):
            with patch.object(Path, "exists", return_value=False):
                with self.assertRaisesRegex(FileNotFoundError, "没有找到 CLI 工具"):
                    resolve_cli_tool("codex")

    def test_resolve_cli_tool_keeps_absolute_path(self) -> None:
        self.assertEqual(resolve_cli_tool("/tmp/codex"), "/tmp/codex")

    def test_launchd_status_reports_configured_schedule(self) -> None:
        config = Config(
            excel_path=Path("/tmp/bugs.xlsx"),
            sheet_name="Sheet1",
            assignee="谢浩杰",
            target_repo=Path("/tmp/repo"),
            target_app_path="apps/pc-web",
            worktree_root=Path("/tmp/worktrees"),
            runs_root=Path("/tmp/logs"),
            logs_root=Path("/tmp/logs"),
            launchd_label="local.test",
            cli_tool="codex",
            schedule_hour=21,
            schedule_minute=30,
            approval_web_port=8765,
            approval_api_port=8766,
        )
        with patch("bugfix_automation.scheduler.Path.exists", return_value=False):
            status = launchd_status(config)

        self.assertFalse(status["installed"])
        self.assertFalse(status["loaded"])
        self.assertEqual(status["schedule_hour"], 21)
        self.assertEqual(status["schedule_minute"], 30)

    def test_install_launchd_at_writes_custom_schedule(self) -> None:
        config = Config(
            excel_path=Path("/tmp/bugs.xlsx"),
            sheet_name="Sheet1",
            assignee="谢浩杰",
            target_repo=Path("/tmp/repo"),
            target_app_path="apps/pc-web",
            worktree_root=Path("/tmp/worktrees"),
            runs_root=Path("/tmp/logs"),
            logs_root=Path("/tmp/logs"),
            launchd_label="local.test",
            cli_tool="/tmp/codex",
            schedule_hour=22,
            schedule_minute=0,
            approval_web_port=8765,
            approval_api_port=8766,
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "local.test.plist"
            with patch("bugfix_automation.scheduler.plist_path", return_value=path):
                with patch("bugfix_automation.scheduler.subprocess.run") as run:
                    install_launchd_at(config, 8, 45)

            payload = plistlib.loads(path.read_bytes())

        self.assertEqual(payload["StartCalendarInterval"], {"Hour": 8, "Minute": 45})
        self.assertEqual(run.call_count, 2)

    def test_uninstall_launchd_removes_plist(self) -> None:
        config = Config(
            excel_path=Path("/tmp/bugs.xlsx"),
            sheet_name="Sheet1",
            assignee="谢浩杰",
            target_repo=Path("/tmp/repo"),
            target_app_path="apps/pc-web",
            worktree_root=Path("/tmp/worktrees"),
            runs_root=Path("/tmp/logs"),
            logs_root=Path("/tmp/logs"),
            launchd_label="local.test",
            cli_tool="codex",
            schedule_hour=22,
            schedule_minute=0,
            approval_web_port=8765,
            approval_api_port=8766,
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "local.test.plist"
            path.write_text("demo", encoding="utf-8")
            with patch("bugfix_automation.scheduler.plist_path", return_value=path):
                with patch("bugfix_automation.scheduler.subprocess.run") as run:
                    result = uninstall_launchd(config)

        self.assertTrue(result["removed"])
        self.assertFalse(path.exists())
        run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
