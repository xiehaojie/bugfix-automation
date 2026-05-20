# Medium Engineering FastAPI Refactor Design

## Goal

Refactor the project into a standard medium-sized engineering layout while preserving current behavior. The approval console should keep the same workflows: Excel selection and upload, filtered bug listing, manual bug execution, approval/rejection/cleanup, rework, scheduler controls, log viewing, workspace switching, and automation config editing.

The main changes are structural:

- Replace the hand-written approval HTTP API with FastAPI.
- Split backend code by API, application use cases, domain models, and infrastructure adapters.
- Split the Next.js approval page into feature modules, hooks, API client helpers, typed payloads, and reusable UI components.
- Keep endpoint paths and response shapes as compatible as possible so the migration can be verified incrementally.

## Current State

The repository is already split into a Python package and a Next.js frontend:

- Python package: `bugfix_automation/`
- Next app: `approval-web/`
- Main backend API file: `bugfix_automation/approval_api.py`
- Main backend server launcher: `bugfix_automation/approval_server.py`
- Main frontend page: `approval-web/app/page.tsx`
- Main frontend stylesheet: `approval-web/app/globals.css`

The behavior is useful and should be preserved, but several files have too many responsibilities:

- `approval_api.py` handles routing, request parsing, file upload parsing, payload mapping, background task startup, file serving, config updates, and error formatting.
- `page.tsx` contains API calls, page state, polling, form validation, business actions, types, and most UI components.
- `globals.css` contains global tokens and almost all page/component styling.

## Recommended Approach

Use a medium refactor rather than a rewrite. Move code into clearer modules while keeping function-level logic close to the current implementation. The first implementation should avoid changing user-facing flows, endpoint names, command names, config keys, or output directories unless a compatibility shim is provided.

FastAPI is a good fit because it gives structured routing, request validation, multipart uploads, JSON errors, and future OpenAPI documentation without forcing the CLI automation into a web-first architecture.

## Backend Architecture

Target backend layout:

```text
bugfix_automation/
  api/
    __init__.py
    app.py
    dependencies.py
    errors.py
    schemas.py
    routes/
      __init__.py
      approval.py
      bugs.py
      config.py
      excel.py
      logs.py
      scheduler.py
      static_files.py
  application/
    __init__.py
    approval_service.py
    bug_service.py
    config_service.py
    excel_service.py
    log_service.py
    scheduler_service.py
  domain/
    __init__.py
    models.py
  infra/
    __init__.py
    uploads.py
    file_metadata.py
```

Keep existing modules such as `runner.py`, `approval.py`, `scheduler.py`, `config.py`, `filtering.py`, `task_state.py`, `worktree.py`, `excel_reader.py`, and `excel_writer.py` as the core implementation layer at first. The new `application/*_service.py` modules should wrap them into use cases rather than duplicating logic.

### API Layer

`api/app.py` creates the FastAPI app, registers routers, configures CORS for local development, and maps exceptions into the current JSON error shape:

```json
{"ok": false, "error": "ValueError: ..."}
```

Routers should preserve current paths:

- `GET /api/items`
- `GET /api/bugs`
- `GET /api/image?path=...`
- `GET /api/config`
- `GET /api/logs?branch=...`
- `GET /api/scheduler`
- `POST /api/excel/upload`
- `POST /api/excel/select-path`
- `POST /api/bugs/run`
- `POST /api/bugs/delete`
- `POST /api/approve`
- `POST /api/reject`
- `POST /api/cleanup`
- `POST /api/rework`
- `POST /api/scheduler/install`
- `POST /api/scheduler/uninstall`
- `POST /api/run-once`
- `POST /api/workspace/select`
- `POST /api/config/update`

### Application Layer

Application services own workflow-level behavior:

- `ApprovalService`: load fix items, count pending, approve, reject, cleanup, rework.
- `BugService`: list filtered Excel bugs, start one bug in the background, delete/mark a bug processed.
- `ExcelService`: upload files, validate `.xlsx`, select a local path, produce file metadata.
- `ConfigService`: return config payload, switch workspace, update automation prompt/config fields.
- `SchedulerService`: inspect, install, uninstall, and start manual runs.
- `LogService`: return bounded Codex log content.

These services can initially return dictionaries matching the existing frontend contract. Typed response models can be introduced in `api/schemas.py` without forcing every internal function to become Pydantic on day one.

### Domain Layer

Keep this layer thin. It should define shared data shapes only when they are stable and useful across services:

- `ImagePayload`
- `BugPayload`
- `FixItemPayload`
- `ExcelFileMetadata`
- `TaskStatusPayload`

Avoid inventing a large domain model for the entire automation system. Most current behavior is orchestration around files, git, Excel, and subprocesses.

### Infrastructure Layer

Infrastructure helpers should be small and testable:

- `uploads.py`: safe upload filename, upload root, file write, Excel zip validation.
- `file_metadata.py`: size, mtime, sha256.

Existing modules already act as infrastructure adapters for git, Codex, Excel, launchd, and reports. Move them only when needed; broad path churn is not required for this refactor.

## Server Launching

`bugfix_automation.approval_server` should keep its public functions:

- `serve(config, host, port)`
- `serve_api_only(config, host, port)`

Internally, `serve_api_only` should run the FastAPI app through `uvicorn`. `serve` should still start the API and then run the Next dev server exactly like today.

Add backend dependencies in a lightweight project file. Preferred option:

```text
requirements.txt
```

with:

```text
fastapi
uvicorn[standard]
python-multipart
```

If the project later adopts `pyproject.toml`, these can move there. For this migration, `requirements.txt` is enough and matches the local script nature of the repository.

## Frontend Architecture

Target frontend layout:

```text
approval-web/
  app/
    globals.css
    layout.tsx
    page.tsx
  src/
    features/
      approval/
        api.ts
        types.ts
        hooks/
          useApprovalDashboard.ts
          useAutoRefresh.ts
          useLogPolling.ts
        components/
          ApprovalActions.tsx
          AutomationConfigPanel.tsx
          BranchButton.tsx
          BugDocumentPanel.tsx
          BugTable.tsx
          DiffView.tsx
          LogPanel.tsx
          QueueRail.tsx
          ReworkPanel.tsx
          SchedulerPanel.tsx
          TaskState.tsx
          WorkspaceHeader.tsx
    components/
      ui/
        Badge.tsx
        Button.tsx
        Metric.tsx
        Panel.tsx
        TextField.tsx
    lib/
      format.ts
      splitLines.ts
```

`app/page.tsx` should become a composition file. It should wire the approval dashboard hook to feature components and avoid owning all API action details directly.

### Frontend Data Flow

- `features/approval/api.ts` owns `fetchJson` and all endpoint helpers.
- `types.ts` owns all payload types currently embedded in `page.tsx`.
- `useApprovalDashboard` owns dashboard state, selected branch, config form state, scheduler form state, and actions.
- Polling should be split into hooks so interval setup is easy to inspect and test.

The frontend should continue to call the same `/api/...` paths. Upload may still use the explicit API port when needed, but the preferred long-term path is to proxy all API traffic through Next rewrites or a single API base URL helper.

## Frontend Design Guidelines

The approval console is an operational tool, not a marketing page. The design should stay dense, scan-friendly, and predictable.

Use these conventions:

- Page layout: persistent left queue rail, main work area, right inspector on wide screens.
- Mobile layout: stack sections into one column; queue rail becomes non-sticky and full width.
- Radius: 8px max for panels, buttons, inputs, badges, and branch rows.
- Typography: system sans-serif, no viewport-scaled font sizes, no negative letter spacing.
- Colors: neutral background, white surfaces, dark rail, blue action accent, green success, amber running, red danger.
- Components: use icon+text buttons for primary actions, badges for statuses, panels for grouped tools, and code blocks for branches/files/logs.
- `globals.css` should keep only tokens, reset, shell layout, and cross-cutting utilities. Component-specific CSS should move next to component files or into feature CSS modules.

Avoid nested cards. A panel may contain structured controls, but repeated items like branch rows and rule rows should not be wrapped inside extra card layers.

## Compatibility Strategy

The migration should be incremental:

1. Introduce FastAPI dependencies and app skeleton.
2. Move API payload helpers into services while keeping old tests passing.
3. Replace `ThreadingHTTPServer` in `approval_api.py` with a compatibility wrapper around the FastAPI app or retire it after callers are updated.
4. Keep CLI command names unchanged.
5. Split frontend types/API helpers first, then components, then CSS.
6. Run tests after each backend step and run `npm run build` after frontend steps.

Existing tests import private helpers from `approval_api.py`. During migration, either:

- keep small compatibility re-exports in `approval_api.py`, or
- update tests to import from the new service modules.

The safer first step is compatibility re-exports, because it reduces the chance of behavioral drift.

## Error Handling

FastAPI handlers should preserve user-facing error behavior:

- Expected validation and runtime failures return JSON with `ok: false` and a human-readable `error`.
- File download failures return a JSON 404 like today.
- Successful mutation endpoints continue returning `{"ok": true, ...}`.
- Background task failures should still be visible through task state and logs.

## Testing Plan

Backend:

- Keep the existing `python3 -m unittest` suite green.
- Add FastAPI route tests with `fastapi.testclient.TestClient` for representative endpoints:
  - config payload
  - Excel upload validation
  - bug payload
  - scheduler status
  - JSON error shape
- Preserve tests for Excel parsing, filtering, prompt rendering, worktree behavior, scheduler, approval actions, and task state.

Frontend:

- Run `npm run build` from `approval-web`.
- For component extraction, rely on TypeScript build as the first regression guard.
- After the app is split, add targeted tests only if the project adds a frontend test runner. Do not introduce a large testing stack just for this refactor unless the user asks.

Manual verification:

- `python3 -m unittest`
- `python3 -m bugfix_automation.cli approval-api`
- `python3 -m bugfix_automation.cli approval-server`
- Open the console and verify:
  - Excel file metadata loads.
  - filtered bugs load.
  - scheduler controls render.
  - logs poll.
  - approval actions still call the same endpoints.

## Non-Goals

- Do not redesign the product workflow.
- Do not change Excel filter semantics.
- Do not change Codex prompt behavior except by moving code.
- Do not change worktree, branch, report, upload, log, or run directory conventions.
- Do not add authentication; this remains a local-only tool.
- Do not push changes to the target repository.
- Do not introduce a database.
- Do not convert the Python automation into a long-running job system.

## Open Decisions

- Whether to keep `approval_api.py` permanently as a compatibility facade or remove it after tests and CLI imports move.
- Whether to keep plain CSS files or adopt CSS modules for component styles. CSS modules are cleaner for the split, but plain CSS has less migration friction.
- Whether to add `pyproject.toml` now or use `requirements.txt` first. The recommended first step is `requirements.txt`.

