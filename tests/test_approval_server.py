import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from bugfix_automation.approval_server import PortProcess, serve, serve_api_only
from bugfix_automation.config import Config


def _config() -> Config:
    return Config(
        excel_path=Path("/tmp/bugs.xlsx"),
        sheet_name="Sheet1",
        assignee="谢浩杰",
        target_repo=Path("/tmp/repo"),
        target_app_path="apps/pc-web",
        worktree_root=Path("/tmp/worktrees"),
        runs_root=Path("/tmp/runs"),
        logs_root=Path("/tmp/logs"),
        launchd_label="local.test",
        cli_tool="codex",
        schedule_hour=22,
        schedule_minute=0,
        approval_web_port=8765,
        approval_api_port=8766,
    )


class ApprovalServerTest(unittest.TestCase):
    def test_api_only_reports_occupied_port_with_pid(self) -> None:
        output = io.StringIO()
        with patch(
            "bugfix_automation.approval_server._listening_port_processes",
            return_value=[PortProcess(pid="12345", command="python -m bugfix_automation.cli approval-api")],
        ):
            with patch("bugfix_automation.approval_server.serve_api") as serve_api_mock:
                with redirect_stdout(output):
                    with self.assertRaises(SystemExit) as raised:
                        serve_api_only(_config())

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("审批 API 端口 8766 已被占用", output.getvalue())
        self.assertIn("PID 12345", output.getvalue())
        self.assertIn("kill 12345", output.getvalue())
        serve_api_mock.assert_not_called()

    def test_full_server_reports_occupied_web_port_before_starting_frontend(self) -> None:
        calls = []

        def port_processes(port: int):
            calls.append(port)
            if port == 8765:
                return [PortProcess(pid="23456", command="next dev --port 8765")]
            return []

        output = io.StringIO()
        with patch("bugfix_automation.approval_server._listening_port_processes", side_effect=port_processes):
            with patch("bugfix_automation.approval_server._frontend_is_healthy", return_value=False):
                with patch("bugfix_automation.approval_server.threading.Thread") as thread_mock:
                    with patch("bugfix_automation.approval_server.subprocess.run") as run_mock:
                        with redirect_stdout(output):
                            with self.assertRaises(SystemExit) as raised:
                                serve(_config())

        self.assertEqual(raised.exception.code, 2)
        self.assertEqual(calls, [8766, 8765])
        self.assertIn("审批台前端 端口 8765 已被占用", output.getvalue())
        self.assertIn("PID 23456", output.getvalue())
        self.assertIn("kill 23456", output.getvalue())
        thread_mock.assert_not_called()
        run_mock.assert_not_called()

    def test_full_server_reuses_healthy_existing_frontend_and_starts_api(self) -> None:
        calls = []

        def port_processes(port: int):
            calls.append(port)
            if port == 8765:
                return [PortProcess(pid="23456", command="next-server (v16.2.6)")]
            return []

        output = io.StringIO()
        with patch("bugfix_automation.approval_server._listening_port_processes", side_effect=port_processes):
            with patch("bugfix_automation.approval_server._frontend_is_healthy", return_value=True):
                with patch("bugfix_automation.approval_server.threading.Thread") as thread_mock:
                    thread_instance = thread_mock.return_value
                    with patch("bugfix_automation.approval_server.subprocess.run") as run_mock:
                        with redirect_stdout(output):
                            serve(_config())

        self.assertEqual(calls, [8766, 8765])
        self.assertIn("检测到已有审批台前端在运行，复用现有前端，只启动审批 API", output.getvalue())
        self.assertIn("PID 23456", output.getvalue())
        thread_instance.start.assert_called_once()
        thread_instance.join.assert_called_once()
        run_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
