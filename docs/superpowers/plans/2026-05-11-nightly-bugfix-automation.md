# Nightly Bugfix Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local-only automation repository that reads the nightly desktop bug list, filters assigned frontend bugs, runs Codex in isolated worktrees, verifies frontend changes, and commits successful fixes to local `fix/*` branches.

**Architecture:** A dependency-light Python CLI owns Excel parsing, filtering, worktree creation, Codex invocation, verification, commits, scheduling, and reporting. Project-level `.codex/agents/*.toml` files describe the multi-agent roles used by generated Codex prompts.

**Tech Stack:** Python 3 standard library, macOS launchd, git worktrees, Codex CLI, Next.js frontend verification commands from `apps/pc-web/package.json`.

---

## File Structure

- Create `README.md`: operator documentation and manual commands.
- Create `.gitignore`: ignore run logs, caches, and generated worktree output.
- Create `bugfix_automation/__init__.py`: package marker.
- Create `bugfix_automation/config.py`: defaults and environment overrides.
- Create `bugfix_automation/excel_reader.py`: `.xlsx` reader using `zipfile` and XML parsing.
- Create `bugfix_automation/filtering.py`: bug filtering and slug creation.
- Create `bugfix_automation/prompt.py`: generated Codex prompt.
- Create `bugfix_automation/worktree.py`: local worktree and branch management.
- Create `bugfix_automation/runner.py`: command execution, Codex invocation, verification, local commit.
- Create `bugfix_automation/reporter.py`: JSON and Markdown run reports.
- Create `bugfix_automation/scheduler.py`: launchd plist generation and install helper.
- Create `bugfix_automation/cli.py`: command line entry point.
- Create `.codex/agents/*.toml`: multi-agent role definitions.
- Create `tests/*.py`: unit tests for parser, filtering, prompt, and reports.

## Tasks

### Task 1: Repository Baseline

- [ ] Create package directories and baseline docs.
- [ ] Add `.gitignore`.
- [ ] Commit design and plan documents.

### Task 2: Excel Reader With Tests

- [ ] Write tests that build a minimal `.xlsx` fixture with shared strings and sheet rows.
- [ ] Implement workbook/sheet parsing with `zipfile` and `xml.etree.ElementTree`.
- [ ] Verify tests fail before implementation and pass after implementation.

### Task 3: Filtering and Prompt Tests

- [ ] Write tests for the exact filtering rules.
- [ ] Write tests that generated prompts mention `apps/pc-web`, local-only branches, no backend edits, and no push.
- [ ] Implement filtering, slug generation, and prompt rendering.

### Task 4: Runner, Worktree, and Reporting

- [ ] Write tests for dry-run report output and command planning.
- [ ] Implement worktree creation, command execution wrappers, Codex execution, frontend verification, local commit, and report writing.
- [ ] Keep destructive or remote operations out of the code path.

### Task 5: Multi-Agent Config and Scheduling

- [ ] Add `.codex/agents/*.toml` role files.
- [ ] Add launchd plist generation and install command.
- [ ] Document `run-once`, `list --dry-run`, and `install-launchd`.

### Task 6: Verification

- [ ] Run `python3 -m unittest`.
- [ ] Run `python3 -m bugfix_automation.cli list --dry-run`.
- [ ] Inspect `git status` and commit final implementation locally.

