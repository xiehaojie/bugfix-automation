from __future__ import annotations

from dataclasses import dataclass
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse

from bugfix_automation.config import Config
from bugfix_automation.worktree import commit_all, tracked_changed_files


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
        items.append(
            {
                "branch": fix.branch,
                "path": str(fix.path),
                "changed_files": changed_files,
                "pending": bool(changed_files),
                "status": status,
                "diff": app_diff,
            }
        )
    return items


def count_pending(items: list[dict[str, Any]]) -> int:
    return sum(1 for item in items if any(str(path).startswith("apps/pc-web/") for path in item.get("changed_files", [])))


def approve_fix(config: Config, branch: str) -> str:
    fix = _find_fix(config, branch)
    changed_files = tracked_changed_files(fix.path, config.target_app_path)
    if not changed_files:
        raise RuntimeError("No pc-web changes to approve")
    message = f"fix(pc-web): {branch.removeprefix('fix/')}"
    return commit_all(fix.path, message)


def reject_fix(config: Config, branch: str) -> None:
    fix = _find_fix(config, branch)
    subprocess.run(["git", "worktree", "remove", "--force", str(fix.path)], cwd=config.target_repo, check=True)
    subprocess.run(["git", "branch", "-D", branch], cwd=config.target_repo, check=True)


def render_dashboard(config: Config) -> str:
    items = load_fix_items(config)
    pending_count = count_pending(items)
    cards = "\n".join(_render_card(item) for item in items) or '<p class="muted">当前没有 fix worktree。</p>'
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>Bugfix 审批台</title>
  <style>{_css()}</style>
</head>
<body>
  <header>
    <div>
      <h1>Bugfix 审批台</h1>
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
                    raise RuntimeError("Unknown action")
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
  <h3>GitHub 风格 Diff</h3>
  {diff_to_html(item["diff"])}
</section>"""


def _find_fix(config: Config, branch: str) -> FixWorktree:
    for fix in parse_worktree_list(_git(config.target_repo, ["worktree", "list", "--porcelain"])):
        if fix.branch == branch:
            return fix
    raise RuntimeError(f"Fix branch not found: {branch}")


def _git(cwd: Path, args: list[str]) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, check=True)
    return result.stdout


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
