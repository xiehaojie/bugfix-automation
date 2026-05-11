# Nightly Bugfix Automation Design

## Goal

Build an independent local automation repository that reads the desktop bug list every night at 22:00, filters frontend bugs assigned to the default owner, asks Codex to analyze and fix each bug in an isolated worktree, verifies the frontend, and commits successful fixes to local `fix/*` branches without pushing to any remote.

## Inputs

- Excel file: `/Users/xiehaojie/Desktop/亦城数智人在线清单.xlsx`
- Worksheet: `在线问题清单`
- Target repository: `/Users/xiehaojie/code/monorepo`
- Frontend app scope: `/Users/xiehaojie/code/monorepo/apps/pc-web`
- Default assignee: `谢浩杰`

## Filtering Rules

The automation locates columns by header name instead of hard-coded letters. It keeps rows where:

- `对接人` equals the configured assignee, default `谢浩杰`
- `对接人状态` is not `已解决`
- `来源系统` is either `小亦PC` or `小亦APP`
- `提出人状态` is either `待处理` or `处理中`

Rows missing required fields are skipped and recorded in the run report.

## Architecture

The repository is a dependency-light Python command line tool. Python is used because its standard library can inspect `.xlsx` files as zipped XML without requiring network-installed packages. The CLI has two entry points:

- `run-once`: parse the current Excel file, process matching rows, and write a report
- `install-launchd`: write a user-level macOS LaunchAgent plist for daily 22:00 execution

The automation never changes backend code. The generated Codex prompt explicitly limits edits to `apps/pc-web` and instructs Codex to inspect other files only when needed for context.

## Components

- `bugfix_automation.config`: immutable defaults and environment overrides
- `bugfix_automation.excel_reader`: reads workbook metadata, shared strings, sheet data, and converts Excel serial dates when possible
- `bugfix_automation.filtering`: applies the row filters and creates stable bug records
- `bugfix_automation.worktree`: creates one worktree per bug from the target monorepo and a local branch named `fix/<slug>`
- `bugfix_automation.codex_runner`: calls `codex exec` with a generated prompt and project-level subagent instructions
- `bugfix_automation.verifier`: runs frontend verification commands inside each worktree
- `bugfix_automation.git_ops`: commits successful local fixes only, with no push path
- `bugfix_automation.reporter`: writes JSON and Markdown reports under `runs/YYYY-MM-DD/`

## Multi-Agent Shape

The automation repository includes project-level Codex subagents under `.codex/agents/` using the `.toml` structure from VoltAgent's Codex subagent collection:

- `bug-triage-agent`: classify the Excel row, identify likely frontend areas, and reject backend-only work
- `frontend-fix-agent`: implement the smallest frontend-only fix in `apps/pc-web`
- `verification-agent`: run lint/build checks, inspect diffs, and call out regressions
- `branch-commit-agent`: confirm branch naming, local-only commit behavior, and report output

The main generated prompt explicitly asks Codex to coordinate these roles. Codex subagents are not expected to auto-spawn.

## Scheduling

The first version uses a user-level macOS LaunchAgent:

- Label: `local.bugfix-automation.nightly`
- Start time: 22:00 daily
- Command: repository-local Python module invocation
- Logs: `logs/launchd.out.log` and `logs/launchd.err.log`

The installer writes the plist to `~/Library/LaunchAgents/local.bugfix-automation.nightly.plist` and loads it with `launchctl`. It does not push code or alter the target monorepo remote.

## Failure Handling

Each bug is isolated. If one bug fails Codex execution, verification, or commit, the automation records the failure and continues to the next bug. Existing branches or worktree directories are skipped by default to avoid overwriting manual work. Generated reports include the Excel row number, branch name, status, log path, and failure reason.

## Verification

The automation repository includes unit tests for:

- Excel workbook parsing from a minimal `.xlsx` fixture
- bug filtering rules
- branch slug generation
- Codex prompt content restrictions
- report output shape

Manual verification for the first version is:

- `python3 -m unittest`
- `python3 -m bugfix_automation.cli list --dry-run`

The real nightly command is intentionally separated from the dry run so the Excel parser and filters can be validated before creating worktrees or invoking Codex.

