# Medium Engineering FastAPI Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the approval console into a medium-sized engineering layout with a FastAPI backend and modular Next.js frontend while preserving current behavior.

**Architecture:** Keep current automation modules as the core behavior layer, add FastAPI route and service modules around them, then split the frontend page into typed API helpers, hooks, components, and focused styles. Preserve existing `/api/...` endpoint paths and CLI commands during migration.

**Tech Stack:** Python 3, FastAPI, Uvicorn, python-multipart, unittest, Next.js 16, React 19, TypeScript, CSS modules or focused feature CSS.

---

## File Structure

- Create `requirements.txt`: backend web dependencies.
- Create `bugfix_automation/api/app.py`: FastAPI app factory and router registration.
- Create `bugfix_automation/api/dependencies.py`: request-time config dependency.
- Create `bugfix_automation/api/errors.py`: JSON exception handler compatible with the current API.
- Create `bugfix_automation/api/routes/*.py`: route handlers grouped by feature.
- Create `bugfix_automation/api/schemas.py`: Pydantic request models for mutation endpoints.
- Create `bugfix_automation/application/*.py`: workflow service modules that wrap existing implementation functions.
- Create `bugfix_automation/infra/file_metadata.py`: file metadata helper.
- Create `bugfix_automation/infra/uploads.py`: upload validation and storage helper.
- Modify `bugfix_automation/approval_api.py`: compatibility facade for old imports and `serve_api`.
- Modify `bugfix_automation/approval_server.py`: run FastAPI through Uvicorn.
- Modify `tests/test_approval.py`: keep helper tests green through compatibility exports.
- Create `tests/test_fastapi_api.py`: route-level regression tests.
- Create `approval-web/src/features/approval/types.ts`: frontend payload types.
- Create `approval-web/src/features/approval/api.ts`: endpoint helpers.
- Create `approval-web/src/features/approval/hooks/*.ts`: dashboard, refresh, and log polling hooks.
- Create `approval-web/src/features/approval/components/*.tsx`: approval feature components.
- Create `approval-web/src/components/ui/*.tsx`: shared UI components.
- Create `approval-web/src/lib/*.ts`: formatting and text helpers.
- Modify `approval-web/app/page.tsx`: compose the new feature modules.
- Modify `approval-web/app/globals.css`: retain global tokens/layout only and import feature styles if needed.

## Task 1: Baseline and FastAPI Dependency Setup

**Files:**
- Create: `requirements.txt`
- Test: existing test suite

- [ ] Run `python3 -m unittest` to capture the committed baseline. Expected: all current tests pass or any pre-existing failure is recorded before refactoring.
- [ ] Create `requirements.txt` with:

```text
fastapi
uvicorn[standard]
python-multipart
```

- [ ] Run `python3 -m pip install -r requirements.txt` if FastAPI is not available locally.
- [ ] Run `python3 -m unittest` again. Expected: dependency file does not change behavior.

## Task 2: Extract Backend Infrastructure Helpers

**Files:**
- Create: `bugfix_automation/infra/__init__.py`
- Create: `bugfix_automation/infra/file_metadata.py`
- Create: `bugfix_automation/infra/uploads.py`
- Modify: `bugfix_automation/approval_api.py`
- Test: `tests/test_approval.py`

- [ ] Add a test in `tests/test_approval.py` that imports `_file_metadata`, `_safe_upload_name`, and `_upload_excel` from `bugfix_automation.approval_api` to prove compatibility stays intact.
- [ ] Run `python3 -m unittest tests.test_approval.ApprovalTest.test_upload_excel_accepts_multipart_without_cgi`. Expected: pass before extraction.
- [ ] Move file metadata hashing into `bugfix_automation/infra/file_metadata.py`:

```python
from __future__ import annotations

from datetime import datetime
import hashlib
from pathlib import Path
from typing import Any


def file_metadata(path: Path, original_name: str = "") -> dict[str, Any]:
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
```

- [ ] Move upload filename generation and upload storage into `bugfix_automation/infra/uploads.py`, preserving the current safe-name and `.xlsx` zip validation behavior.
- [ ] Update `approval_api.py` to import and re-export the helpers so current tests and private imports continue to work.
- [ ] Run `python3 -m unittest tests.test_approval`. Expected: pass.

## Task 3: Add Application Services

**Files:**
- Create: `bugfix_automation/application/__init__.py`
- Create: `bugfix_automation/application/approval_service.py`
- Create: `bugfix_automation/application/bug_service.py`
- Create: `bugfix_automation/application/config_service.py`
- Create: `bugfix_automation/application/excel_service.py`
- Create: `bugfix_automation/application/log_service.py`
- Create: `bugfix_automation/application/scheduler_service.py`
- Modify: `bugfix_automation/approval_api.py`
- Test: `tests/test_approval.py`

- [ ] Add service tests or update existing helper tests so `_bug_payload`, `_config_payload`, and `_log_payload` still return the same dictionary shapes.
- [ ] Run the targeted tests. Expected: pass before route migration.
- [ ] Implement services as thin functions around existing modules:
  - `approval_service.list_items`, `approve`, `reject`, `cleanup`, `rework`
  - `bug_service.list_bug_payloads`, `start_bug_run`, `delete_bug`
  - `config_service.config_payload`, `select_workspace`, `update_automation_config`
  - `excel_service.upload_excel`, `select_excel_path`
  - `log_service.log_payload`
  - `scheduler_service.status`, `install`, `uninstall`, `start_once`
- [ ] Update `approval_api.py` helper functions to delegate to the new services.
- [ ] Run `python3 -m unittest tests.test_approval tests.test_config tests.test_scheduler`. Expected: pass.

## Task 4: Introduce FastAPI App and Route Tests

**Files:**
- Create: `bugfix_automation/api/__init__.py`
- Create: `bugfix_automation/api/app.py`
- Create: `bugfix_automation/api/dependencies.py`
- Create: `bugfix_automation/api/errors.py`
- Create: `bugfix_automation/api/schemas.py`
- Create: `bugfix_automation/api/routes/approval.py`
- Create: `bugfix_automation/api/routes/bugs.py`
- Create: `bugfix_automation/api/routes/config.py`
- Create: `bugfix_automation/api/routes/excel.py`
- Create: `bugfix_automation/api/routes/logs.py`
- Create: `bugfix_automation/api/routes/scheduler.py`
- Create: `bugfix_automation/api/routes/static_files.py`
- Create: `tests/test_fastapi_api.py`

- [ ] Write `tests/test_fastapi_api.py` using `fastapi.testclient.TestClient` and dependency override for config.
- [ ] Add route tests for:
  - `GET /api/logs` with an empty branch
  - `GET /api/config`
  - `GET /api/image` rejecting paths outside `runs_root`
  - JSON error shape for invalid local Excel path
- [ ] Run `python3 -m unittest tests.test_fastapi_api`. Expected: fail because app does not exist.
- [ ] Implement `create_app(config=None)` in `api/app.py` and route modules using application services.
- [ ] Run `python3 -m unittest tests.test_fastapi_api`. Expected: pass.
- [ ] Run `python3 -m unittest`. Expected: pass.

## Task 5: Switch Server Startup to FastAPI

**Files:**
- Modify: `bugfix_automation/approval_api.py`
- Modify: `bugfix_automation/approval_server.py`
- Modify: `README.md`
- Test: CLI import and route tests

- [ ] Keep `bugfix_automation.approval_api.serve_api(config, host, port)` as the public entry point.
- [ ] Implement `serve_api` with `uvicorn.run(create_app(config), host=host, port=port)`.
- [ ] Keep `approval_server.serve` behavior: start API in a daemon thread, then run the Next dev server.
- [ ] Update README dependency/setup notes to mention `requirements.txt`.
- [ ] Run `python3 -m unittest tests.test_fastapi_api tests.test_approval`. Expected: pass.
- [ ] Run `python3 -m bugfix_automation.cli approval-api --help`. Expected: CLI help succeeds without starting the server.

## Task 6: Extract Frontend Types, API Helpers, and Utility Functions

**Files:**
- Create: `approval-web/src/features/approval/types.ts`
- Create: `approval-web/src/features/approval/api.ts`
- Create: `approval-web/src/lib/format.ts`
- Create: `approval-web/src/lib/splitLines.ts`
- Modify: `approval-web/app/page.tsx`
- Test: frontend build

- [ ] Move all payload types from `page.tsx` into `types.ts`.
- [ ] Move `fetchJson` and endpoint-specific calls into `api.ts`.
- [ ] Move `formatBytes`, `compactPath`, and related pure helpers into `src/lib/format.ts`.
- [ ] Move `splitLines` into `src/lib/splitLines.ts`.
- [ ] Update `page.tsx` imports without changing rendered behavior.
- [ ] Run `cd approval-web && npm run build`. Expected: pass.

## Task 7: Extract Frontend UI Components

**Files:**
- Create: `approval-web/src/components/ui/Badge.tsx`
- Create: `approval-web/src/components/ui/Button.tsx`
- Create: `approval-web/src/components/ui/Metric.tsx`
- Create: `approval-web/src/components/ui/Panel.tsx`
- Create: `approval-web/src/features/approval/components/*.tsx`
- Modify: `approval-web/app/page.tsx`
- Test: frontend build

- [ ] Move generic UI pieces first: `Badge`, `Metric`, `Panel`.
- [ ] Move feature pieces in small batches: queue rail, header, bug document panel, scheduler panel, bug table, approval actions, rework panel, diff view, log panel, config panel, task state.
- [ ] Keep props explicit and typed from `features/approval/types.ts`.
- [ ] Run `cd approval-web && npm run build` after each batch. Expected: pass.

## Task 8: Extract Frontend State Hooks and Styles

**Files:**
- Create: `approval-web/src/features/approval/hooks/useApprovalDashboard.ts`
- Create: `approval-web/src/features/approval/hooks/useAutoRefresh.ts`
- Create: `approval-web/src/features/approval/hooks/useLogPolling.ts`
- Create: `approval-web/src/features/approval/approval.css`
- Modify: `approval-web/app/page.tsx`
- Modify: `approval-web/app/globals.css`
- Test: frontend build

- [ ] Move dashboard state and actions into `useApprovalDashboard`.
- [ ] Move polling intervals into focused hooks.
- [ ] Keep `page.tsx` as composition only.
- [ ] Move feature-specific CSS from `globals.css` into `features/approval/approval.css` and import it from `page.tsx`.
- [ ] Leave tokens, reset, body, and shell-level primitives in `globals.css`.
- [ ] Run `cd approval-web && npm run build`. Expected: pass.

## Task 9: Final Verification

**Files:**
- All modified files

- [ ] Run `python3 -m unittest`. Expected: all backend tests pass.
- [ ] Run `cd approval-web && npm run build`. Expected: Next build passes.
- [ ] Run `python3 -m bugfix_automation.cli list --dry-run` only if the configured Excel path exists locally. Expected: dry-run reports are generated without starting Codex.
- [ ] Run `git status --short` and review the final changed-file list.
- [ ] Summarize backend structure, frontend structure, and any verification command that could not be run.

