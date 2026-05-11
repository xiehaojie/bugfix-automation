# Nightly Bugfix Automation

Local automation for reading `/Users/xiehaojie/Desktop/亦城数智人在线清单.xlsx`, filtering assigned frontend bugs, running Codex in one worktree per bug, verifying `apps/pc-web`, and committing successful fixes to local `fix/*` branches.

It never pushes to a remote.

The runner enforces that in code:

- Codex runs with `--sandbox workspace-write --ask-for-approval never`.
- `PATH` is prefixed with a local `git` wrapper that blocks `git push`.
- Each temporary worktree gets a local `pre-push` hook that exits non-zero.
- Before verification and commit, the runner rejects any changed path outside `apps/pc-web`, except copied `.codex/agents/*.toml` files.
- The same path check runs again after lint/build and immediately before commit.
- Commits stage only `apps/pc-web`.
- Screenshots from `截图1` / `截图2` / `截图3` cells are extracted from WPS `DISPIMG` images and passed to Codex with `--image`.

## Defaults

- Assignee: `谢浩杰`
- Sheet: `在线问题清单`
- Target repo: `/Users/xiehaojie/code/monorepo`
- Frontend scope: `apps/pc-web`
- Bugfix worktrees: this repository's `.target-worktrees/`
- Schedule: every day at 22:00

Environment overrides:

```bash
BUGFIX_EXCEL_PATH=/path/to/list.xlsx
BUGFIX_ASSIGNEE=谢浩杰
BUGFIX_TARGET_REPO=/Users/xiehaojie/code/monorepo
BUGFIX_TARGET_APP_PATH=apps/pc-web
BUGFIX_WORKTREE_ROOT=/Users/xiehaojie/code/bugfix-automation/.target-worktrees
```

## Commands

List matching rows and write a dry-run report:

```bash
python3 -m bugfix_automation.cli list --dry-run
```

Run the full automation once:

```bash
python3 -m bugfix_automation.cli run-once
```

Install the macOS user LaunchAgent:

```bash
python3 -m bugfix_automation.cli install-launchd
```

The LaunchAgent writes logs to `logs/launchd.out.log` and `logs/launchd.err.log`.

## Filtering

Rows are kept when all of these are true:

- `对接人` is the configured assignee
- `对接人状态` is not `已解决`
- `来源系统` is `小亦PC` or `小亦APP`
- `提出人状态` is `待处理` or `处理中`

## Output

Each run writes:

- `runs/YYYY-MM-DD/report.json`
- `runs/YYYY-MM-DD/report.md`
- `runs/YYYY-MM-DD/approval.md`
- `runs/YYYY-MM-DD/images/<branch>/...`

Successful bug fixes are committed locally in the target monorepo worktree branch named like `fix/bug-87-...`.

The runner copies this repository's `.codex/agents/*.toml` files into each temporary business worktree before invoking Codex, so project-level subagents are available during the fix. Those copied files are not committed; only `apps/pc-web` changes are staged.

If a branch or worktree already exists, the run skips that row and records the existing path or branch instead of overwriting it.

## Morning Approval

The next morning, open `runs/YYYY-MM-DD/approval.md`. It lists each bug with:

- Excel row and issue id
- local `fix/*` branch
- local commit hash
- screenshot paths
- changed `apps/pc-web` files
- diff stat
- conflict risks when two or more committed bug branches touched the same file

The automation does not merge fixes into your main pc-web branch. Each bug is isolated in its own worktree and branch, so multiple bugs can modify the same file overnight without overwriting each other. If `approval.md` reports a conflict risk, review and merge or cherry-pick those branches one at a time.
