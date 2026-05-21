import subprocess
import tempfile
import unittest
import unittest.mock
import json
from pathlib import Path

from fastapi.testclient import TestClient

from bugfix_automation.api.app import create_app
from bugfix_automation.config import Config
from bugfix_automation.storage.repositories import create_ai_session, create_operation, finish_ai_session


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
            data_root=root / "data",
            storage_db_path=root / "data" / "app.sqlite3",
        )

    def test_logs_endpoint_returns_empty_payload_without_branch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = TestClient(create_app(self.make_config(Path(tmp))), raise_server_exceptions=False)

            response = client.get("/api/logs")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"branch": "", "path": "", "content": ""})

    def test_logs_stream_returns_snapshot_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = self.make_config(root)
            log_path = config.logs_root / "codex" / "fix-1-demo.log"
            log_path.parent.mkdir(parents=True)
            log_path.write_text("hello\n", encoding="utf-8")
            client = TestClient(create_app(config), raise_server_exceptions=False)

            response = client.get("/api/logs/stream", params={"branch": "fix/1-demo", "follow": "false"})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/event-stream"))
        self.assertIn('"type":"snapshot"', response.text)
        self.assertIn('"branch":"fix/1-demo"', response.text)
        self.assertIn("hello", response.text)

    def test_logs_stream_allows_localhost_frontend_cors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = self.make_config(root)
            log_path = config.logs_root / "codex" / "fix-1-demo.log"
            log_path.parent.mkdir(parents=True)
            log_path.write_text("hello\n", encoding="utf-8")
            client = TestClient(create_app(config), raise_server_exceptions=False)

            response = client.get(
                "/api/logs/stream",
                params={"branch": "fix/1-demo", "follow": "false"},
                headers={"Origin": "http://127.0.0.1:8765"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["access-control-allow-origin"], "http://127.0.0.1:8765")

    def test_history_endpoint_returns_operations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = self.make_config(Path(tmp))
            operation_id = create_operation(
                config.storage_db_path,
                kind="fix-reject",
                workspace_id="pc-web",
                status="rejected",
                branch="fix/1-demo",
                issue_id="1",
                summary=json.dumps({"title": "已拒绝并删除修复", "diff_preview": "diff --git a/a b/a"}),
            )
            client = TestClient(create_app(config), raise_server_exceptions=False)

            response = client.get("/api/history/operations")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("items", payload)
        self.assertIsInstance(payload["items"], list)
        self.assertEqual(payload["items"][0]["id"], operation_id)
        self.assertEqual(payload["items"][0]["summary_text"], "已拒绝并删除修复")
        self.assertEqual(payload["stats"]["rejected"], 1)

    def test_history_detail_returns_diff_and_ai_previews(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = self.make_config(root)
            operation_id = create_operation(
                config.storage_db_path,
                kind="fix-rework",
                workspace_id="pc-web",
                status="succeeded",
                branch="fix/1-demo",
                summary=json.dumps({"title": "重新修改完成", "changed_files": ["apps/pc-web/a.tsx"], "diff_preview": "+new"}),
            )
            prompt_path = root / "prompt.txt"
            log_path = root / "ai.log"
            prompt_path.write_text("修复输入框", encoding="utf-8")
            log_path.write_text("AI 修改了 a.tsx", encoding="utf-8")
            session_id = create_ai_session(
                config.storage_db_path,
                operation_id=operation_id,
                provider="local-cli",
                cli_tool="codex",
                workspace_path=root / "worktree",
                prompt_path=prompt_path,
                log_path=log_path,
            )
            finish_ai_session(config.storage_db_path, ai_session_id=session_id, status="succeeded", log_path=log_path, summary={"branch": "fix/1-demo"})
            client = TestClient(create_app(config), raise_server_exceptions=False)

            response = client.get(f"/api/history/operations/{operation_id}")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["diff_preview"], "+new")
        self.assertEqual(payload["changed_files"], ["apps/pc-web/a.tsx"])
        self.assertIn("修复输入框", payload["ai_sessions"][0]["prompt_preview"])
        self.assertIn("AI 修改了 a.tsx", payload["ai_sessions"][0]["log_preview"])

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
