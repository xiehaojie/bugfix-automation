import subprocess
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from fastapi.testclient import TestClient

from bugfix_automation.api.app import create_app
from bugfix_automation.config import Config


class FastApiApprovalTest(unittest.TestCase):
    def make_config(self, root: Path) -> Config:
        return Config(
            excel_path=root / "bugs.xlsx",
            sheet_name="Sheet1",
            assignee="谢浩杰",
            target_repo=root / "repo",
            target_app_path="apps/pc-web",
            worktree_root=root / "worktrees",
            runs_root=root / "runs",
            logs_root=root / "logs",
            launchd_label="local.test",
            cli_tool="codex",
            schedule_hour=22,
            schedule_minute=0,
            approval_web_port=8765,
            approval_api_port=8766,
        )

    def test_logs_endpoint_returns_empty_payload_without_branch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = TestClient(create_app(self.make_config(Path(tmp))), raise_server_exceptions=False)

            response = client.get("/api/logs")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"branch": "", "path": "", "content": ""})

    def test_config_endpoint_returns_current_config_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            client = TestClient(create_app(self.make_config(root)))

            response = client.get("/api/config")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["target_app_path"], "apps/pc-web")
        self.assertEqual(payload["api_port"], 8766)
        self.assertEqual(payload["excel_file"], {})

    def test_image_endpoint_rejects_paths_outside_runs_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside = root / "outside.png"
            outside.write_bytes(b"not allowed")
            client = TestClient(create_app(self.make_config(root)))

            response = client.get(f"/api/image?path={outside}")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "图片不存在或不允许访问")

    def test_json_error_shape_for_invalid_excel_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = TestClient(create_app(self.make_config(Path(tmp))), raise_server_exceptions=False)

            response = client.post("/api/excel/select-path", json={"path": "/missing/bugs.xlsx"})

        self.assertEqual(response.status_code, 500)
        self.assertFalse(response.json()["ok"])
        self.assertIn("ValueError:", response.json()["error"])

    def test_file_content_resolves_worktree_for_slash_branch_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = self.make_config(root)
            repo = config.target_repo
            worktree = config.worktree_root / "fix-1-demo"
            repo.mkdir(parents=True)
            subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
            app_file = repo / "apps" / "pc-web" / "src" / "a.tsx"
            app_file.parent.mkdir(parents=True)
            app_file.write_text("initial\n", encoding="utf-8")
            subprocess.run(["git", "add", "apps/pc-web/src/a.tsx"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["git", "worktree", "add", str(worktree), "-b", "fix/1-demo"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
            (worktree / "apps" / "pc-web" / "src" / "a.tsx").write_text("from worktree\n", encoding="utf-8")
            client = TestClient(create_app(config))

            response = client.get(
                "/api/file-content",
                params={"branch": "fix/1-demo", "path": "apps/pc-web/src/a.tsx"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"ok": True, "content": "from worktree\n"})

    def test_approval_api_module_is_only_a_fastapi_facade(self) -> None:
        source = Path("bugfix_automation/approval_api.py").read_text(encoding="utf-8")

        self.assertNotIn("BaseHTTPRequestHandler", source)
        self.assertNotIn("ThreadingHTTPServer", source)
        self.assertNotIn("def _bug_payload", source)
        self.assertNotIn("def _upload_excel", source)

    def test_approval_api_server_uses_live_config_loader_after_startup(self) -> None:
        from bugfix_automation.approval_api import serve_api

        with tempfile.TemporaryDirectory() as tmp:
            config = self.make_config(Path(tmp))
            with unittest.mock.patch("bugfix_automation.approval_api.uvicorn.run") as run:
                serve_api(config)

        app = run.call_args.args[0]
        self.assertIsNone(app.state.config)


if __name__ == "__main__":
    unittest.main()
