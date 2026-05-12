from __future__ import annotations

from dataclasses import dataclass
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import subprocess
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse

from bugfix_automation.config import Config
from bugfix_automation.excel_writer import update_cell_by_header
from bugfix_automation.runner import list_bugs
from bugfix_automation.runner import assert_scope_clean, codex_command, codex_log_path
from bugfix_automation.task_state import is_task_active, set_task_state, task_state
from bugfix_automation.worktree import changed_paths, commit_all, create_no_push_git_wrapper, tracked_changed_files


@dataclass(frozen=True)
class FixWorktree:
    path: Path
    branch: str


def parse_worktree_list(output: str) -> list[FixWorktree]:
    fixes: list[FixWorktree] = []
    current_path: Path | None = None
    for line in output.splitlines():
        if line.startswith("worktree "):
            current_path = Path(line.removeprefix("worktree "))
        elif line.startswith("branch refs/heads/") and current_path is not None:
            branch = line.removeprefix("branch refs/heads/")
            if branch.startswith("fix/"):
                fixes.append(FixWorktree(path=current_path, branch=branch))
    return fixes


def load_fix_items(config: Config) -> list[dict[str, Any]]:
    output = _git(config.target_repo, ["worktree", "list", "--porcelain"])
    items: list[dict[str, Any]] = []
    for fix in parse_worktree_list(output):
        changed_files = tracked_changed_files(fix.path, config.target_app_path)
        app_diff = _git(fix.path, ["diff", "--", config.target_app_path])
        status = _git(fix.path, ["status", "--short", "--", config.target_app_path])
        state = task_state(config, fix.branch)
        active = is_task_active(config, fix.branch)
        items.append(
            {
                "branch": fix.branch,
                "path": str(fix.path),
                "changed_files": changed_files,
                "pending": bool(changed_files),
                "active": active,
                "task_status": state.get("status", ""),
                "task_phase": state.get("phase", ""),
                "task_detail": state.get("detail", ""),
                "task_updated_at": state.get("updated_at", ""),
                "status": status,
                "diff": app_diff,
                "log_path": str(codex_log_path(config, fix.branch)),
            }
        )
    return items


def count_pending(items: list[dict[str, Any]]) -> int:
    return sum(1 for item in items if bool(item.get("active")) or bool(item.get("pending")) or bool(item.get("changed_files")))


def approve_fix(config: Config, branch: str) -> str:
    if is_task_active(config, branch):
        state = task_state(config, branch)
        raise RuntimeError(f"任务仍在执行中，不能审批提交：{state.get('status', '')}/{state.get('phase', '')}")
    fix = _find_fix(config, branch)
    changed_files = tracked_changed_files(fix.path, config.target_app_path)
    if not changed_files:
        raise RuntimeError("没有可审批的 pc-web 改动")
    scope = config.target_app_path.rstrip("/").split("/")[-1] or "frontend"
    message = f"fix({scope}): {branch.removeprefix('fix/')}"
    commit = commit_all(fix.path, message, config.target_app_path)
    mark_excel_processed(config, branch)
    remove_worktree(config, branch)
    return commit


def reject_fix(config: Config, branch: str) -> None:
    if is_task_active(config, branch):
        state = task_state(config, branch)
        raise RuntimeError(f"任务仍在执行中，不能拒绝删除：{state.get('status', '')}/{state.get('phase', '')}")
    fix = _find_fix(config, branch)
    remove_worktree(config, branch)
    subprocess.run(["git", "branch", "-D", branch], cwd=config.target_repo, check=True)


def remove_worktree(config: Config, branch: str) -> None:
    fix = _find_fix(config, branch)
    subprocess.run(["git", "worktree", "remove", "--force", str(fix.path)], cwd=config.target_repo, check=True)


def mark_excel_processed(config: Config, branch: str) -> bool:
    state = task_state(config, branch)
    if state.get("excel_row"):
        update_cell_by_header(
            config.excel_path,
            config.sheet_name,
            int(state["excel_row"]),
            config.excel_processed_status_column,
            config.excel_processed_status_value,
        )
        return True
    branch_issue_id = _branch_issue_id(branch)
    for bug in list_bugs(config):
        if branch_issue_id and bug.issue_id == branch_issue_id:
            update_cell_by_header(
                config.excel_path,
                config.sheet_name,
                bug.excel_row,
                config.excel_processed_status_column,
                config.excel_processed_status_value,
            )
            return True
    return False


def _branch_issue_id(branch: str) -> str:
    if branch.startswith("fix/bug-"):
        without_prefix = branch.removeprefix("fix/bug-")
        prefix, separator, stamp = without_prefix.rpartition("-")
        if separator and re.fullmatch(r"\d{12}", stamp):
            return prefix.split("-", 1)[0]
    if branch.startswith("fix/"):
        return branch.removeprefix("fix/").split("-", 1)[0]
    return ""


def rework_fix(config: Config, branch: str, note: str = "", file_paths: list[str] | None = None, image_paths: list[str] | None = None) -> None:
    if is_task_active(config, branch):
        state = task_state(config, branch)
        raise RuntimeError(f"任务仍在执行中，不能重新修改：{state.get('status', '')}/{state.get('phase', '')}")
    fix = _find_fix(config, branch)
    normalized_images = [Path(path).expanduser() for path in image_paths or [] if path.strip()]
    prompt = _rework_prompt(config, branch, note, file_paths or [], normalized_images)
    git_wrapper_dir = create_no_push_git_wrapper(fix.path)
    set_task_state(config, branch, "reworking", detail="正在根据补充信息重新修改。", phase="codex", image_paths=normalized_images)
    try:
        _run(codex_command(config.codex_bin, str(fix.path), prompt, normalized_images), cwd=fix.path, path_prefix=git_wrapper_dir, stdin_text=prompt, log_path=codex_log_path(config, branch))
        assert_scope_clean(changed_paths(fix.path), config.target_app_path)
        _git(fix.path, ["diff", "--check", "--", config.target_app_path])
        set_task_state(config, branch, "pending-approval", detail="重新修改完成，等待审批。", phase="done", image_paths=normalized_images)
    except Exception as exc:
        set_task_state(config, branch, "failed", detail=f"{type(exc).__name__}: {exc}", phase="failed", image_paths=normalized_images)
        raise


def render_dashboard(config: Config) -> str:
    items = load_fix_items(config)
    pending_count = count_pending(items)
    cards = "\n".join(_render_card(item) for item in items) or '<p class="muted">当前没有待审批的 fix 工作目录。</p>'
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>Bug 修复审批台</title>
  <style>{_css()}</style>
</head>
<body>
  <header>
    <div>
      <h1>Bug 修复审批台</h1>
      <p>当前有 <strong>{pending_count}</strong> 个修改待处理</p>
    </div>
    <a class="button secondary" href="/">刷新</a>
  </header>
  <main>{cards}</main>
</body>
</html>"""


def diff_to_html(diff_text: str) -> str:
    if not diff_text.strip():
        return '<p class="muted">没有 pc-web diff。</p>'
    lines = []
    for raw in diff_text.splitlines():
        klass = "diff-line"
        if raw.startswith("+") and not raw.startswith("+++"):
            klass = "diff-line diff-line-add"
        elif raw.startswith("-") and not raw.startswith("---"):
            klass = "diff-line diff-line-del"
        elif raw.startswith("@@"):
            klass = "diff-line diff-line-hunk"
        elif raw.startswith("diff --git"):
            klass = "diff-line diff-line-file"
        lines.append(f'<tr class="{klass}"><td><pre>{escape(raw)}</pre></td></tr>')
    return f'<table class="diff"><tbody>{"".join(lines)}</tbody></table>'


def serve(config: Config, host: str = "127.0.0.1", port: int = 8765) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self._send_html(render_dashboard(config))

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            branch = unquote(params.get("branch", [""])[0])
            try:
                if parsed.path == "/approve":
                    approve_fix(config, branch)
                elif parsed.path == "/reject":
                    reject_fix(config, branch)
                else:
                    raise RuntimeError("未知操作")
                self.send_response(303)
                self.send_header("Location", "/")
                self.end_headers()
            except Exception as exc:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(exc).encode("utf-8"))

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _send_html(self, html: str) -> None:
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    items = load_fix_items(config)
    print(f"审批台启动：当前有 {count_pending(items)} 个修改待处理")
    print(f"打开：http://{host}:{port}")
    ThreadingHTTPServer((host, port), Handler).serve_forever()


def _render_card(item: dict[str, Any]) -> str:
    branch = item["branch"]
    quoted = quote(branch, safe="")
    changed = "".join(f"<li>{escape(path)}</li>" for path in item["changed_files"]) or "<li>无</li>"
    approve_disabled = "" if item["pending"] else "disabled"
    return f"""<section class="card">
  <div class="card-head">
    <div>
      <h2>{escape(branch)}</h2>
      <p class="muted">{escape(item["path"])}</p>
    </div>
    <div class="actions">
      <form method="post" action="/approve?branch={quoted}"><button {approve_disabled}>审批通过并提交</button></form>
      <form method="post" action="/reject?branch={quoted}"><button class="danger">拒绝并删除</button></form>
    </div>
  </div>
  <h3>改动文件</h3>
  <ul>{changed}</ul>
  <h3>类似 GitHub 的代码比对</h3>
  {diff_to_html(item["diff"])}
</section>"""


def _find_fix(config: Config, branch: str) -> FixWorktree:
    for fix in parse_worktree_list(_git(config.target_repo, ["worktree", "list", "--porcelain"])):
        if fix.branch == branch:
            return fix
    raise RuntimeError(f"没有找到修复分支: {branch}")


def _git(cwd: Path, args: list[str]) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, check=True)
    return result.stdout


def _run(command: list[str], cwd: Path, path_prefix: Path | None = None, stdin_text: str | None = None, log_path: Path | None = None) -> None:
    import os

    env = os.environ.copy()
    if path_prefix is not None:
        env["PATH"] = f"{path_prefix}{os.pathsep}{env.get('PATH', '')}"
    if log_path is None:
        subprocess.run(command, cwd=cwd, env=env, input=stdin_text, text=stdin_text is not None, check=True)
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write(f"\n$ {' '.join(command)}\n")
        log_file.flush()
        subprocess.run(command, cwd=cwd, env=env, input=stdin_text, text=stdin_text is not None, stdout=log_file, stderr=subprocess.STDOUT, check=True)


def _rework_prompt(config: Config, branch: str, note: str, file_paths: list[str], image_paths: list[Path]) -> str:
    files = "\n".join(f"- {path}" for path in file_paths if path.strip()) or "- 无"
    images = "\n".join(f"- {path}" for path in image_paths) or "- 无"
    return f"""你正在继续修改一个已经由自动化创建的前端 bug 修复分支。

分支: {branch}
前端范围: {config.target_app_path}

请根据下面的补充信息重新分析并修改。要求：
- 只修改 {config.target_app_path} 范围内的前端代码。
- 不要修改后端，不要 push，不要合并到主分支。
- 如果补充文件路径存在，请读取它们作为上下文。
- 如果传入了图片，请结合图片理解问题。
- 修改后请尽量运行与该改动相关的检查；如果依赖缺失，请在最终说明中写清楚。

补充文字:
{note or "无"}

补充文件路径:
{files}

补充图片路径:
{images}
"""


def _css() -> str:
    return """
body{margin:0;background:#f6f8fa;color:#1f2328;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
header{position:sticky;top:0;z-index:1;display:flex;justify-content:space-between;align-items:center;padding:18px 28px;background:#fff;border-bottom:1px solid #d0d7de}
h1{margin:0;font-size:22px} h2{margin:0;font-size:18px} h3{font-size:14px;margin:18px 0 8px}
main{max-width:1180px;margin:24px auto;padding:0 20px}
.card{background:#fff;border:1px solid #d0d7de;border-radius:8px;margin-bottom:18px;overflow:hidden}
.card-head{display:flex;justify-content:space-between;gap:16px;padding:16px;border-bottom:1px solid #d0d7de}
.muted{color:#656d76;font-size:13px}.actions{display:flex;gap:8px;align-items:flex-start}
button,.button{border:1px solid #1f883d;background:#1f883d;color:#fff;border-radius:6px;padding:7px 12px;font-size:13px;text-decoration:none;cursor:pointer}
button:disabled{opacity:.45;cursor:not-allowed}.secondary{border-color:#d0d7de;background:#f6f8fa;color:#24292f}.danger{border-color:#cf222e;background:#cf222e}
ul{margin:0 16px 14px 34px;padding:0}.diff{width:100%;border-collapse:collapse;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px}
.diff pre{margin:0;white-space:pre-wrap}.diff-line td{padding:2px 10px;border-top:1px solid #f0f0f0}.diff-line-add{background:#dafbe1}.diff-line-del{background:#ffebe9}.diff-line-hunk{background:#ddf4ff;color:#0969da}.diff-line-file{background:#f6f8fa;font-weight:600}
"""
