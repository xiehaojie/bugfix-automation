from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from typing import Any
from urllib.parse import urlparse

from bugfix_automation.approval import approve_fix, count_pending, load_fix_items, reject_fix, remove_worktree, rework_fix
from bugfix_automation.config import Config


def serve_api(config: Config, host: str = "127.0.0.1", port: int | None = None) -> None:
    api_port = port or config.approval_api_port

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/api/items":
                    items = load_fix_items(config)
                    self._send_json({"pending_count": count_pending(items), "items": items})
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

    print(f"审批 API 启动：http://{host}:{api_port}")
    ThreadingHTTPServer((host, api_port), Handler).serve_forever()


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]
