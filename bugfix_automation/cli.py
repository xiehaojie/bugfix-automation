from __future__ import annotations

import argparse
import json

from bugfix_automation.config import load_config
from bugfix_automation.filtering import make_branch_name
from bugfix_automation.runner import list_bugs, run_once
from bugfix_automation.scheduler import install_launchd


def main() -> int:
    parser = argparse.ArgumentParser(description="Nightly frontend bugfix automation")
    subparsers = parser.add_subparsers(dest="command", required=True)
    list_parser = subparsers.add_parser("list", help="List matching bugs")
    list_parser.add_argument("--dry-run", action="store_true", help="Also write a dry-run report")
    subparsers.add_parser("run-once", help="Run the full automation once")
    subparsers.add_parser("install-launchd", help="Install the daily 22:00 LaunchAgent")
    args = parser.parse_args()

    config = load_config()
    if args.command == "list":
        bugs = list_bugs(config)
        print(json.dumps([{"issue_id": bug.issue_id, "row": bug.excel_row, "branch": make_branch_name(bug), "description": bug.description} for bug in bugs], ensure_ascii=False, indent=2))
        if args.dry_run:
            json_path, md_path, approval_path = run_once(config, dry_run=True)
            print(f"Dry-run report: {json_path}")
            print(f"Dry-run markdown: {md_path}")
            print(f"Dry-run approval: {approval_path}")
        return 0
    if args.command == "run-once":
        json_path, md_path, approval_path = run_once(config)
        print(f"Report: {json_path}")
        print(f"Markdown: {md_path}")
        print(f"Approval: {approval_path}")
        return 0
    if args.command == "install-launchd":
        path = install_launchd(config)
        print(f"Installed LaunchAgent: {path}")
        return 0
    parser.error("Unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
