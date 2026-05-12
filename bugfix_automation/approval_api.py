from __future__ import annotations

from email import policy
from email.parser import BytesParser
from datetime import datetime
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import re
import threading
import zipfile
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

from bugfix_automation.approval import approve_fix, count_pending, load_fix_items, reject_fix, remove_worktree, rework_fix
from bugfix_automation.config import Config, load_config, repo_root_path, update_config_yaml
from bugfix_automation.filtering import make_branch_name
from bugfix_automation.images import export_bug_images
from bugfix_automation.runner import codex_log_path, list_bugs, run_one
from bugfix_automation.scheduler import install_launchd_at, launchd_status, start_manual_run, uninstall_launchd
from bugfix_automation.task_state import is_task_active, set_task_state, task_state
from bugfix_automation.excel_writer import update_cell_by_header


def serve_api(config: Config, host: str = "127.0.0.1", port: int | None = None) -> None:
    api_port = port or config.approval_api_port

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            try:
                active_config = load_config()
                if parsed.path == "/api/items":
                    items = load_fix_items(active_config)
                    self._send_json({"pending_count": count_pending(items), "items": items})
                elif parsed.path == "/api/bugs":
                    self._send_json({"bugs": _bug_payload(active_config)})
                elif parsed.path == "/api/image":
                    params = parse_qs(parsed.query)
                    self._send_file(active_config, params.get("path", [""])[0])
                elif parsed.path == "/api/config":
                    self._send_json(_config_payload(active_config))
                elif parsed.path == "/api/logs":
                    params = parse_qs(parsed.query)
                    self._send_json(_log_payload(active_config, params.get("branch", [""])[0]))
                elif parsed.path == "/api/scheduler":
                    self._send_json(launchd_status(active_config))
                else:
                    self._send_json({"error": "接口不存在"}, status=404)
            except Exception as exc:
                self._send_error(exc)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            try:
                active_config = load_config()
                if parsed.path == "/api/excel/upload":
                    self._send_json(_upload_excel(self))
                    return
                payload = self._read_json()
                branch = str(payload.get("branch", ""))
                if parsed.path == "/api/excel/select-path":
                    self._send_json(_select_excel_path(str(payload.get("path", ""))))
                elif parsed.path == "/api/bugs/run":
                    self._send_json(_start_bug_run(active_config, int(payload.get("excel_row", 0) or 0)))
                elif parsed.path == "/api/bugs/delete":
                    self._send_json(_delete_bug(active_config, int(payload.get("excel_row", 0) or 0)))
                elif parsed.path == "/api/approve":
                    commit = approve_fix(active_config, branch)
                    self._send_json({"ok": True, "commit": commit})
                elif parsed.path == "/api/reject":
                    reject_fix(active_config, branch)
                    self._send_json({"ok": True})
                elif parsed.path == "/api/cleanup":
                    remove_worktree(active_config, branch)
                    self._send_json({"ok": True})
                elif parsed.path == "/api/rework":
                    rework_fix(
                        active_config,
                        branch,
                        note=str(payload.get("note", "")),
                        file_paths=_string_list(payload.get("file_paths")),
                        image_paths=_string_list(payload.get("image_paths")),
                    )
                    self._send_json({"ok": True})
                elif parsed.path == "/api/scheduler/install":
                    hour = int(payload.get("hour", active_config.schedule_hour))
                    minute = int(payload.get("minute", active_config.schedule_minute))
                    update_config_yaml({"schedule": {"hour": hour, "minute": minute}})
                    next_config = load_config()
                    path = install_launchd_at(next_config, hour, minute)
                    self._send_json({"ok": True, "plist_path": str(path), "status": launchd_status(next_config)})
                elif parsed.path == "/api/scheduler/uninstall":
                    result = uninstall_launchd(active_config)
                    self._send_json({"ok": True, "result": result, "status": launchd_status(load_config())})
                elif parsed.path == "/api/run-once":
                    self._send_json({"ok": True, "run": start_manual_run(active_config)})
                elif parsed.path == "/api/workspace/select":
                    workspace_id = str(payload.get("workspace_id", ""))
                    if not any(workspace.id == workspace_id for workspace in active_config.workspaces):
                        raise ValueError(f"未知工作区: {workspace_id}")
                    update_config_yaml({"active_workspace": workspace_id})
                    self._send_json({"ok": True, "config": _config_payload(load_config())})
                elif parsed.path == "/api/config/update":
                    updates: dict[str, Any] = {}
                    if "max_concurrency" in payload:
                        updates["max_concurrency"] = int(payload["max_concurrency"])
                    if "branch_summary_fields" in payload:
                        updates["branch_summary_fields"] = payload["branch_summary_fields"]
                    if "prompt" in payload and isinstance(payload["prompt"], dict):
                        updates["prompt"] = payload["prompt"]
                    update_config_yaml(updates)
                    self._send_json({"ok": True, "config": _config_payload(load_config())})
                else:
                    self._send_json({"error": "接口不存在"}, status=404)
            except Exception as exc:
                self._send_error(exc)

        def do_OPTIONS(self) -> None:  # noqa: N802
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

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


def _upload_excel(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    content_type = handler.headers.get("Content-Type", "")
    if "multipart/form-data" not in content_type:
        raise ValueError("请使用表单上传 xlsx 文件")
    content_length = int(handler.headers.get("Content-Length", "0"))
    body = handler.rfile.read(content_length) if content_length > 0 else handler.rfile.read()
    filename, file_bytes = _extract_multipart_file(body, content_type)
    if not filename:
        raise ValueError("没有收到文件")
    original_name = Path(filename).name
    if not original_name.lower().endswith(".xlsx"):
        raise ValueError("只支持 .xlsx 文件")
    uploads_root = repo_root_path() / "uploads"
    uploads_root.mkdir(parents=True, exist_ok=True)
    safe_name = _safe_upload_name(original_name)
    target = uploads_root / safe_name
    target.write_bytes(file_bytes)
    if not zipfile.is_zipfile(target):
        target.unlink(missing_ok=True)
        raise ValueError("上传的 xlsx 文件不完整或不是有效的 Excel 文件；请重新上传原始 .xlsx 文件")
    update_config_yaml({"excel_path": target})
    return {
        "ok": True,
        "excel_path": str(target),
        "filename": original_name,
        "file": _file_metadata(target, original_name=original_name),
        "config": {"excel_path": str(target)},
    }


def _extract_multipart_file(body: bytes, content_type: str) -> tuple[str, bytes]:
    message = BytesParser(policy=policy.default).parsebytes(
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8") + body
    )
    if not message.is_multipart():
        raise ValueError("没有收到文件")
    for part in message.iter_parts():
        if part.get_content_disposition() != "form-data":
            continue
        if part.get_param("name", header="content-disposition") != "file":
            continue
        filename = part.get_filename() or ""
        payload = part.get_payload(decode=True) or b""
        if filename:
            return filename, payload
    raise ValueError("没有收到文件")


def _select_excel_path(raw_path: str) -> dict[str, Any]:
    path = Path(raw_path).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"文件不存在: {path}")
    if path.suffix.lower() != ".xlsx":
        raise ValueError("只支持 .xlsx 文件")
    if not zipfile.is_zipfile(path):
        raise ValueError("选择的 xlsx 文件不完整或不是有效的 Excel 文件")
    update_config_yaml({"excel_path": path})
    return {"ok": True, "excel_path": str(path), "file": _file_metadata(path)}


def _safe_upload_name(original_name: str) -> str:
    stem = Path(original_name).stem or "bugs"
    safe_stem = re.sub(r"[^\w\u4e00-\u9fff.-]+", "-", stem).strip(".-") or "bugs"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    return f"{safe_stem}-{stamp}.xlsx"


def _file_metadata(path: Path, original_name: str = "") -> dict[str, Any]:
    stat = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "path": str(path),
        "original_name": original_name or path.name,
        "stored_name": path.name,
        "size": stat.st_size,
        "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        "sha256": digest.hexdigest(),
    }


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _start_bug_run(config: Config, excel_row: int) -> dict[str, Any]:
    bug = _bug_by_row(config, excel_row)
    branch = make_branch_name(bug, config.branch_summary_fields, datetime.now().strftime("%Y%m%d%H%M"))
    if is_task_active(config, branch):
        state = task_state(config, branch)
        return {"ok": True, "branch": branch, "status": state.get("status", "running"), "message": "任务已在执行中"}
    set_task_state(config, branch, "queued", bug, detail="用户从审批台手动执行。", phase="queued")
    thread = threading.Thread(target=_run_bug_background, args=(config, bug.excel_row), daemon=True)
    thread.start()
    return {"ok": True, "branch": branch, "excel_row": bug.excel_row, "status": "queued"}


def _run_bug_background(config: Config, excel_row: int) -> None:
    run_one(config, excel_row=excel_row)


def _delete_bug(config: Config, excel_row: int) -> dict[str, Any]:
    bug = _bug_by_row(config, excel_row)
    branch = make_branch_name(bug, config.branch_summary_fields, datetime.now().strftime("%Y%m%d%H%M"))
    if is_task_active(config, branch):
        state = task_state(config, branch)
        raise RuntimeError(f"任务仍在执行中，不能删除：{state.get('status', '')}/{state.get('phase', '')}")
    update_cell_by_header(
        config.excel_path,
        config.sheet_name,
        bug.excel_row,
        config.excel_processed_status_column,
        config.excel_processed_status_value,
    )
    set_task_state(config, branch, "deleted", bug, detail="用户从审批台删除；Excel 已标记为已处理。", phase="done")
    return {"ok": True, "branch": branch, "excel_row": bug.excel_row}


def _bug_by_row(config: Config, excel_row: int):
    if excel_row <= 0:
        raise ValueError("缺少 Excel 行号")
    for bug in list_bugs(config):
        if bug.excel_row == excel_row:
            return bug
    raise ValueError(f"当前筛选结果中没有 Excel 第 {excel_row} 行")


def _config_payload(config: Config) -> dict[str, Any]:
    return {
        "target_repo": str(config.target_repo),
        "target_app_path": config.target_app_path,
        "excel_path": str(config.excel_path),
        "excel_file": _file_metadata(config.excel_path) if config.excel_path.exists() else {},
        "assignee": config.assignee,
        "web_port": config.approval_web_port,
        "api_port": config.approval_api_port,
        "active_workspace": config.active_workspace,
        "max_concurrency": config.max_concurrency,
        "workspaces": [
            {
                "id": workspace.id,
                "name": workspace.name,
                "target_repo": str(workspace.target_repo),
                "target_app_path": workspace.target_app_path,
                "scope_paths": list(workspace.scope_paths),
                "verify_commands": [" ".join(command) for command in workspace.verify_commands],
                "prompt_context_paths": list(workspace.prompt_context_paths),
                "max_concurrency": workspace.max_concurrency,
            }
            for workspace in config.workspaces
        ],
        "filters": [
            {"field": rule.field, "op": rule.op, "value": rule.value, "values": list(rule.values)}
            for rule in config.filters
        ],
        "branch_summary_fields": list(config.branch_summary_fields),
        "prompt": {
            "fields": list(config.prompt_fields),
            "template": config.prompt_template,
            "context_paths": list(config.prompt_context_paths),
        },
    }


def _log_payload(config: Config, branch: str) -> dict[str, Any]:
    if not branch:
        return {"branch": "", "path": "", "content": ""}
    path = codex_log_path(config, branch)
    if not path.exists():
        return {"branch": branch, "path": str(path), "content": ""}
    content = path.read_text(encoding="utf-8", errors="replace")
    return {"branch": branch, "path": str(path), "content": content[-120000:]}


def _bug_payload(config: Config) -> list[dict[str, Any]]:
    bugs = list_bugs(config)
    payload: list[dict[str, Any]] = []
    stamp = datetime.now().strftime("%Y%m%d%H%M")
    for bug in bugs:
        branch = make_branch_name(bug, config.branch_summary_fields, stamp)
        state = task_state(config, branch)
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
            "active": is_task_active(config, branch),
            "task_status": state.get("status", ""),
            "task_phase": state.get("phase", ""),
            "task_detail": state.get("detail", ""),
            "task_updated_at": state.get("updated_at", ""),
            "images": [
                {"path": str(path), "name": path.name, "url": f"/api/image?path={quote(str(path), safe='')}"}
                for path in images
            ],
        }
        )
    return payload
