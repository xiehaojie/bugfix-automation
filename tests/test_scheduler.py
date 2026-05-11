import unittest
from pathlib import Path
from unittest.mock import patch

from bugfix_automation.config import Config
from bugfix_automation.scheduler import launchd_status, resolve_codex_bin


class SchedulerTest(unittest.TestCase):
    def test_resolve_codex_bin_fails_without_absolute_path(self) -> None:
        with patch("bugfix_automation.scheduler.shutil.which", return_value=None):
            with patch.object(Path, "exists", return_value=False):
                with self.assertRaisesRegex(FileNotFoundError, "没有找到 Codex CLI"):
                    resolve_codex_bin("codex")

    def test_resolve_codex_bin_keeps_absolute_path(self) -> None:
        self.assertEqual(resolve_codex_bin("/tmp/codex"), "/tmp/codex")

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
            codex_bin="codex",
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


if __name__ == "__main__":
    unittest.main()
