from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

from bugfix_automation.approval import approve_fix, count_pending, load_fix_items, reject_fix, remove_worktree, rework_fix
from bugfix_automation.config import Config
from bugfix_automation.filtering import make_branch_name
from bugfix_automation.images import export_bug_images
from bugfix_automation.runner import list_bugs


def serve_api(config: Config, host: str = "127.0.0.1", port: int | None = None) -> None:
    api_port = port or config.approval_api_port

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/api/items":
                    items = load_fix_items(config)
                    self._send_json({"pending_count": count_pending(items), "items": items})
                elif parsed.path == "/api/bugs":
                    self._send_json({"bugs": _bug_payload(config)})
                elif parsed.path == "/api/image":
                    params = parse_qs(parsed.query)
                    self._send_file(config, params.get("path", [""])[0])
                elif parsed.path == "/api/config":
                    self._send_json(
                        {
                            "target_repo": str(config.target_repo),
                            "target_app_path": config.target_app_path,
                            "excel_path": str(config.excel_path),
                            "assignee": config.assignee,
                            "web_port": config.approval_web_port,
                            "api_port": config.approval_api_port,
                        }
                    )
                else:
                    self._send_json({"error": "接口不存在"}, status=404)
            except Exception as exc:
                self._send_error(exc)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            try:
                payload = self._read_json()
                branch = str(payload.get("branch", ""))
                if parsed.path == "/api/approve":
                    commit = approve_fix(config, branch)
                    self._send_json({"ok": True, "commit": commit})
                elif parsed.path == "/api/reject":
                    reject_fix(config, branch)
                    self._send_json({"ok": True})
                elif parsed.path == "/api/cleanup":
                    remove_worktree(config, branch)
                    self._send_json({"ok": True})
                elif parsed.path == "/api/rework":
                    rework_fix(
                        config,
                        branch,
                        note=str(payload.get("note", "")),
                        file_paths=_string_list(payload.get("file_paths")),
                        image_paths=_string_list(payload.get("image_paths")),
                    )
                    self._send_json({"ok": True})
                else:
                    self._send_json({"error": "接口不存在"}, status=404)
            except Exception as exc:
                self._send_error(exc)

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                return {}
            return json.loads(self.rfile.read(length).decode("utf-8"))

        def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_error(self, exc: Exception) -> None:
            self._send_json({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, status=500)

        def _send_file(self, config: Config, raw_path: str) -> None:
            path = Path(raw_path).expanduser().resolve()
            allowed_root = config.runs_root.resolve()
            if not path.is_file() or allowed_root not in [path, *path.parents]:
                self._send_json({"error": "图片不存在或不允许访问"}, status=404)
                return
            body = path.read_bytes()
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    print(f"审批 API 启动：http://{host}:{api_port}")
    ThreadingHTTPServer((host, api_port), Handler).serve_forever()


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _bug_payload(config: Config) -> list[dict[str, Any]]:
    bugs = list_bugs(config)
    payload: list[dict[str, Any]] = []
    for bug in bugs:
        branch = make_branch_name(bug)
        images = export_bug_images(config.excel_path, bug, config.runs_root / "approval-images" / branch.replace("/", "-"))
        payload.append(
            {
            "issue_id": bug.issue_id,
            "excel_row": bug.excel_row,
            "branch": branch,
            "source_system": bug.source_system,
            "priority": bug.priority,
            "primary_category": bug.primary_category,
            "secondary_category": bug.secondary_category,
            "requester": bug.requester,
            "request_date": bug.request_date,
            "requester_status": bug.requester_status,
            "assignee": bug.assignee,
            "assignee_status": bug.assignee_status,
            "resolved_date": bug.resolved_date,
            "description": bug.description,
            "remark": bug.remark,
            "remark2": bug.remark2,
            "images": [
                {"path": str(path), "name": path.name, "url": f"/api/image?path={quote(str(path), safe='')}"}
                for path in images
            ],
        }
        )
    return payload
