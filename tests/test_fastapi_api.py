import subprocess
import tempfile
import unittest
import unittest.mock
import json
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from bugfix_automation.api.app import create_app
from bugfix_automation.config import Config, WorkspaceConfig
from bugfix_automation.storage.db import connect
from bugfix_automation.storage.repositories import create_ai_session, create_operation, finish_ai_session
from bugfix_automation.storage.settings import get_setting
from tests.test_excel_reader import write_minimal_xlsx


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

    def test_preview_prompt_honors_empty_prompt_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workbook = root / "bugs.xlsx"
            write_minimal_xlsx(workbook)
            config = replace(
                self.make_config(root),
                excel_path=workbook,
                sheet_name="在线问题清单",
                prompt_fields=(),
                workspaces=(
                    WorkspaceConfig(
                        id="pc-web",
                        name="PC Web",
                        target_repo=root / "repo",
                        target_app_path="apps/pc-web",
                        scope_paths=("apps/pc-web",),
                        verify_commands=(),
                        prompt_context_paths=(),
                        max_concurrency=2,
                    ),
                ),
            )
            client = TestClient(create_app(config), raise_server_exceptions=False)

            response = client.post("/api/bugs/preview-prompt", json={"excel_row": 2})

        self.assertEqual(response.status_code, 200)
        prompt = response.json()["prompt"]
        self.assertIn("Capability system: Codex + Superpowers", prompt)
        selected_section = prompt.split("原始 Excel 行完整信息：", 1)[0]
        self.assertIn("Excel 选中字段：\n- 无", selected_section)
        self.assertNotIn("问题描述: 账号离线状态", selected_section)
        self.assertIn("问题描述: 账号离线状态", prompt)

    def test_config_payload_includes_capability_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = self.make_config(root)
            client = TestClient(create_app(config), raise_server_exceptions=False)

            response = client.get("/api/config")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("capability_status", payload)
        self.assertIn(payload["capability_status"]["provider"], {"codex", "claude"})
        self.assertIn("warnings", payload["capability_status"])

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

    def test_history_detail_falls_back_to_commit_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = self.make_config(root)
            repo = config.target_repo
            app_file = repo / "apps" / "pc-web" / "src" / "a.tsx"
            app_file.parent.mkdir(parents=True)
            subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
            app_file.write_text("before\n", encoding="utf-8")
            subprocess.run(["git", "add", "apps/pc-web/src/a.tsx"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
            app_file.write_text("after\n", encoding="utf-8")
            subprocess.run(["git", "add", "apps/pc-web/src/a.tsx"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "fix"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
            commit_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
            operation_id = create_operation(
                config.storage_db_path,
                kind="fix-commit",
                workspace_id="pc-web",
                status="committed",
                branch="fix/1-demo",
                summary=json.dumps({"title": "已提交此修复", "commit_sha": commit_sha}),
            )
            client = TestClient(create_app(config), raise_server_exceptions=False)

            response = client.get(f"/api/history/operations/{operation_id}")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("+after", payload["diff_preview"])
        self.assertEqual(payload["changed_files"], ["apps/pc-web/src/a.tsx"])

    def test_history_groups_commit_back_to_run_record_by_issue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = self.make_config(root)
            older_run_id = create_operation(
                config.storage_db_path,
                kind="run_one",
                workspace_id="pc-web",
                status="succeeded",
                branch="fix/bug-28-App中无法通过键盘tab键一键输入-202605211409",
                issue_id="28",
                excel_row=156,
                summary="已生成待审批改动",
            )
            latest_run_id = create_operation(
                config.storage_db_path,
                kind="run_one",
                workspace_id="pc-web",
                status="succeeded",
                branch="fix/bug-28-App中无法通过键盘tab键一键输入-202605211424",
                issue_id="28",
                excel_row=156,
                summary="已生成待审批改动",
            )
            commit_id = create_operation(
                config.storage_db_path,
                kind="fix-commit",
                workspace_id="pc-web",
                status="committed",
                branch="fix/28-新增技能建议点击填入入口",
                summary=json.dumps({"title": "已提交此修复", "commit_sha": "abc123"}),
            )
            with connect(config.storage_db_path) as db:
                db.execute("UPDATE operations SET started_at = ?, ended_at = ? WHERE id = ?", ("2026-05-21T14:09:26", "2026-05-21T14:16:59", older_run_id))
                db.execute("UPDATE operations SET started_at = ?, ended_at = ? WHERE id = ?", ("2026-05-21T14:24:07", "2026-05-21T14:33:41", latest_run_id))
                db.execute("UPDATE operations SET started_at = ?, ended_at = ? WHERE id = ?", ("2026-05-21 06:37:23", "2026-05-21 06:37:23", commit_id))
                db.commit()
            config.runs_root.mkdir(parents=True)
            (config.runs_root / "task-state.json").write_text(
                json.dumps(
                    {
                        "tasks": {
                            "fix/28-新增技能建议点击填入入口": {
                                "branch": "fix/28-新增技能建议点击填入入口",
                                "issue_id": "28",
                                "excel_row": 156,
                                "operation_id": latest_run_id,
                                "description": "在App中无法通过键盘tab键一键输入",
                            }
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            client = TestClient(create_app(config), raise_server_exceptions=False)

            response = client.get("/api/history/operations")
            detail = client.get(f"/api/history/operations/{latest_run_id}")

        self.assertEqual(response.status_code, 200)
        items = response.json()["items"]
        item = items[0]
        self.assertEqual(item["id"], latest_run_id)
        self.assertEqual(item["kind"], "fix-commit")
        self.assertEqual(item["status"], "committed")
        self.assertEqual(item["branch"], "fix/28-新增技能建议点击填入入口")
        self.assertEqual(item["original_branch"], "fix/bug-28-App中无法通过键盘tab键一键输入-202605211424")
        self.assertEqual(item["issue_id"], "28")
        self.assertEqual(item["excel_row"], 156)
        self.assertEqual(item["summary_text"], "已提交此修复")
        self.assertEqual(items[1]["id"], older_run_id)
        self.assertEqual(items[1]["kind"], "run_one")
        self.assertEqual(response.json()["stats"]["submitted"], 1)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["operation"]["kind"], "fix-commit")
        self.assertEqual(len(detail.json()["related_operations"]), 2)

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

    def test_config_update_persists_cli_tool_setting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = self.make_config(root)
            client = TestClient(create_app(config), raise_server_exceptions=False)
            with unittest.mock.patch.dict("os.environ", {"BUGFIX_STORAGE_DB_PATH": str(config.storage_db_path)}):
                response = client.post("/api/config/update", json={"cli_tool": "/usr/local/bin/codex"})

            self.assertEqual(response.status_code, 200)
            self.assertEqual(get_setting(config.storage_db_path, "automation"), {"cli_tool": "/usr/local/bin/codex"})

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

    def test_excel_adapter_analyze_endpoint_returns_cleaned_suggestion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = replace(self.make_config(root), sheet_name="在线问题清单")
            write_minimal_xlsx(config.excel_path)
            client = TestClient(create_app(config), raise_server_exceptions=False)
            proc = unittest.mock.Mock()
            proc.returncode = 0
            proc.communicate = unittest.mock.AsyncMock(
                return_value=(
                    json.dumps(
                        {
                            "canonical_fields": {"issue_id": "序号", "description": "问题描述"},
                            "prompt": {"fields": ["问题描述"], "template": "专用模板"},
                            "branch_summary_fields": ["问题描述"],
                            "filters": [],
                            "warnings": [],
                        },
                        ensure_ascii=False,
                    ).encode(),
                    b"",
                )
            )
            with unittest.mock.patch(
                "bugfix_automation.application.excel_adapter_service.asyncio.create_subprocess_exec",
                new=unittest.mock.AsyncMock(return_value=proc),
            ):
                response = client.post("/api/excel/adapter/analyze")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["adapter"]["canonical_fields"]["description"], "问题描述")

    def test_online_sheet_providers_endpoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = TestClient(create_app(self.make_config(Path(tmp))), raise_server_exceptions=False)

            response = client.get("/api/online-sheets/providers")

        self.assertEqual(response.status_code, 200)
        providers = {item["key"] for item in response.json()["providers"]}
        self.assertGreaterEqual(providers, {"feishu", "dingtalk", "tencent_docs", "wps"})

    def test_online_sheet_preview_returns_json_error_without_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            client = TestClient(create_app(self.make_config(Path(tmp))), raise_server_exceptions=False)

            response = client.post(
                "/api/online-sheets/preview",
                json={
                    "provider": "feishu",
                    "url": "https://example.feishu.cn/sheets/abc123",
                    "range": "A1:C10",
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])
        self.assertIn("飞书", response.json()["error"])

    def test_excel_adapter_save_endpoint_persists_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = replace(self.make_config(root), sheet_name="在线问题清单")
            write_minimal_xlsx(config.excel_path)
            client = TestClient(create_app(config), raise_server_exceptions=False)

            response = client.post(
                "/api/excel/adapter/save",
                json={
                    "adapter": {
                        "canonical_fields": {"issue_id": "序号", "description": "问题描述"},
                        "prompt": {"fields": ["问题描述"], "template": "专用模板"},
                        "branch_summary_fields": ["问题描述"],
                        "filters": [{"field": "提出人状态", "op": "not_in", "values": ["已解决"]}],
                    }
                },
            )

            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()["ok"])
            self.assertEqual(
                get_setting(config.storage_db_path, "excel_profile")["canonical_fields"],
                {"issue_id": "序号", "description": "问题描述"},
            )

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
