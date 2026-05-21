from __future__ import annotations

import argparse
import json
from datetime import datetime

from bugfix_automation.config import load_config
from bugfix_automation.filtering import make_branch_name
from bugfix_automation.runner import list_bugs, run_once, run_one
from bugfix_automation.scheduler import install_launchd_at
from bugfix_automation.storage.settings import get_setting, set_setting
from bugfix_automation.approval_server import serve, serve_api_only
from bugfix_automation.application import integration_service


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
    # Integration subcommands
    int_parser = subparsers.add_parser("integration", help="本地 PR 集成队列操作")
    int_sub = int_parser.add_subparsers(dest="int_command", required=True)
    int_create = int_sub.add_parser("create", help="创建集成单")
    int_create.add_argument("--target-branch", required=True, help="目标分支")
    int_create.add_argument("--branches", nargs="+", required=True, help="待集成的 fix/* 分支")
    int_create.add_argument("--workspace", default=None, help="workspace ID")
    int_sub.add_parser("list", help="列出所有集成单")
    int_start = int_sub.add_parser("start", help="开始集成")
    int_start.add_argument("run_id", help="集成单 ID")
    int_confirm = int_sub.add_parser("confirm", help="确认提交")
    int_confirm.add_argument("run_id", help="集成单 ID")
    int_cleanup = int_sub.add_parser("cleanup", help="清理已合入来源分支")
    int_cleanup.add_argument("run_id", help="集成单 ID")
    int_abort = int_sub.add_parser("abort", help="中止集成")
    int_abort.add_argument("run_id", help="集成单 ID")
    launchd_parser = subparsers.add_parser("install-launchd", help="安装 macOS 定时任务")
    launchd_parser.add_argument("--hour", type=int, default=None, help="每天几点执行，0-23")
    launchd_parser.add_argument("--minute", type=int, default=None, help="每小时第几分钟执行，0-59")
    args = parser.parse_args()

    config = load_config()
    if args.command == "list":
        stamp = datetime.now().strftime("%Y%m%d%H%M")
        bugs = list_bugs(config)
        print(json.dumps([
            {
                "issue_id": bug.issue_id,
                "row": bug.excel_row,
                "branch": make_branch_name(bug, config.branch_summary_fields, stamp),
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
        hour = config.schedule_hour if args.hour is None else args.hour
        minute = config.schedule_minute if args.minute is None else args.minute
        automation = get_setting(config.storage_db_path, "automation", {})
        if not isinstance(automation, dict):
            automation = {}
        set_setting(config.storage_db_path, "automation", {**automation, "schedule": {"hour": hour, "minute": minute}})
        config = load_config()
        path = install_launchd_at(config, hour, minute)
        print(f"已安装定时任务: {path}")
        return 0
    if args.command == "approval-server":
        serve(config, host=args.host, port=args.port)
        return 0
    if args.command == "approval-api":
        serve_api_only(config, host=args.host, port=args.port)
        return 0
    if args.command == "integration":
        return _handle_integration(config, args)
    parser.error("未知命令")
    return 2


def _handle_integration(config, args) -> int:
    if args.int_command == "list":
        runs = integration_service.list_runs(config)
        for run in runs:
            print(f"  {run['run_id']}  [{run['status']}]  target={run['target_branch']}  items={len(run.get('items', []))}")
        if not runs:
            print("没有集成单。")
        return 0
    if args.int_command == "create":
        workspace_id = args.workspace or config.active_workspace
        data = integration_service.create_run(config, workspace_id, args.target_branch, args.branches)
        print(f"已创建集成单: {data['run_id']}")
        print(f"  目标分支: {data['target_branch']}")
        print(f"  集成分支: {data['integration_branch']}")
        print(f"  来源分支: {len(data['items'])} 个")
        return 0
    if args.int_command == "start":
        data = integration_service.start_run(config, args.run_id)
        applied = sum(1 for item in data["items"] if item["status"] == "applied")
        failed = sum(1 for item in data["items"] if item["status"] == "conflict")
        print(f"集成完成: {data['status']}")
        print(f"  应用成功: {applied}  冲突: {failed}")
        print(f"  验证: {data.get('verify', {}).get('status', 'N/A')}")
        return 0
    if args.int_command == "confirm":
        data = integration_service.confirm_run(config, args.run_id)
        print(f"已确认提交: {data['final_commit']}")
        return 0
    if args.int_command == "cleanup":
        data = integration_service.cleanup_run(config, args.run_id)
        cleaned = data.get("cleaned_branches", [])
        print(f"已清理 {len(cleaned)} 个来源分支:")
        for b in cleaned:
            print(f"  - {b}")
        return 0
    if args.int_command == "abort":
        integration_service.abort_run(config, args.run_id)
        print("已中止集成单。")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
