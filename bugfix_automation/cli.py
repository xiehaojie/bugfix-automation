from __future__ import annotations

import argparse
import json

from bugfix_automation.config import load_config
from bugfix_automation.filtering import make_branch_name
from bugfix_automation.runner import list_bugs, run_once, run_one
from bugfix_automation.scheduler import install_launchd
from bugfix_automation.approval_server import serve, serve_api_only


def main() -> int:
    parser = argparse.ArgumentParser(description="夜间前端 bug 自动修复工具")
    subparsers = parser.add_subparsers(dest="command", required=True)
    list_parser = subparsers.add_parser("list", help="列出符合筛选规则的 bug")
    list_parser.add_argument("--dry-run", action="store_true", help="只生成演练报告，不启动 Codex")
    one_parser = subparsers.add_parser("run-one", help="按 Excel 行号或 bug 序号运行一条")
    selector = one_parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--issue-id", help="Excel `序号` 列中的 bug 序号")
    selector.add_argument("--row", type=int, help="Excel 行号")
    one_parser.add_argument("--dry-run", action="store_true", help="只导出截图和报告，不启动 Codex")
    subparsers.add_parser("run-once", help="运行本次筛选出的全部 bug")
    approval_parser = subparsers.add_parser("approval-server", help="启动本地可视化审批台")
    approval_parser.add_argument("--host", default="127.0.0.1")
    approval_parser.add_argument("--port", type=int, default=None)
    approval_api_parser = subparsers.add_parser("approval-api", help="只启动审批 API")
    approval_api_parser.add_argument("--host", default="127.0.0.1")
    approval_api_parser.add_argument("--port", type=int, default=None)
    subparsers.add_parser("install-launchd", help="安装每天 22:00 的 macOS 定时任务")
    args = parser.parse_args()

    config = load_config()
    if args.command == "list":
        bugs = list_bugs(config)
        print(json.dumps([
            {
                "issue_id": bug.issue_id,
                "row": bug.excel_row,
                "branch": make_branch_name(bug),
                "source_system": bug.source_system,
                "primary_category": bug.primary_category,
                "secondary_category": bug.secondary_category,
                "requester": bug.requester,
                "description": bug.description,
                "remark": bug.remark,
                "remark2": bug.remark2,
            }
            for bug in bugs
        ], ensure_ascii=False, indent=2))
        if args.dry_run:
            json_path, md_path, approval_path = run_once(config, dry_run=True)
            print(f"演练 JSON 报告: {json_path}")
            print(f"演练 Markdown 报告: {md_path}")
            print(f"演练审批报告: {approval_path}")
        return 0
    if args.command == "run-once":
        json_path, md_path, approval_path = run_once(config)
        print(f"JSON 报告: {json_path}")
        print(f"Markdown 报告: {md_path}")
        print(f"审批报告: {approval_path}")
        return 0
    if args.command == "run-one":
        json_path, md_path, approval_path = run_one(config, issue_id=args.issue_id, excel_row=args.row, dry_run=args.dry_run)
        print(f"JSON 报告: {json_path}")
        print(f"Markdown 报告: {md_path}")
        print(f"审批报告: {approval_path}")
        return 0
    if args.command == "install-launchd":
        path = install_launchd(config)
        print(f"已安装定时任务: {path}")
        return 0
    if args.command == "approval-server":
        serve(config, host=args.host, port=args.port)
        return 0
    if args.command == "approval-api":
        serve_api_only(config, host=args.host, port=args.port)
        return 0
    parser.error("未知命令")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
