# Lightweight Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a lightweight local storage layer for configuration snapshots, Excel import records, user operations, operation history, and long AI execution records.

**Architecture:** Use SQLite as the queryable metadata store and keep large payloads on disk as artifacts. `config.yaml` remains the human-editable source of truth, while SQLite stores immutable snapshots and operation history. Long AI logs are streamed to files, indexed by byte range, and exposed through paginated/tail APIs instead of being stored as one large database field.

**Tech Stack:** Python stdlib `sqlite3`, `json`, `hashlib`, `pathlib`, existing FastAPI backend, existing pytest suite, existing filesystem roots (`uploads/`, `runs/`, `logs/`).

---

## Storage Shape

Use this local layout:

```text
data/
  app.sqlite3
  app.sqlite3-shm
  app.sqlite3-wal
uploads/
  <existing uploaded excel files>
runs/
  artifacts/
    excel-imports/<import_id>/row-images/...
    operations/<operation_id>/...
logs/
  ai/
    <ai_session_id>/
      full.log
      prompt.txt
      summary.json
```

SQLite stores only small, queryable data:

- IDs, timestamps, user-visible status, branch, workspace, Excel row number.
- JSON snapshots of config and Excel row data.
- Paths, sizes, sha256 hashes, byte offsets, and short summaries for large files.
- Append-only user and system operation events.

Filesystem stores large or replay-oriented data:

- Original Excel files.
- Exported screenshots and binary artifacts.
- Full AI prompts and full AI logs.
- Optional operation attachments.

## File Structure

- Create: `bugfix_automation/storage/__init__.py`
  - Exports storage helpers.
- Create: `bugfix_automation/storage/schema.sql`
  - Owns SQLite schema and indexes.
- Create: `bugfix_automation/storage/db.py`
  - Opens the database, enables WAL, applies schema idempotently, provides transaction helpers.
- Create: `bugfix_automation/storage/artifacts.py`
  - Computes artifact paths, sha256, file metadata, and safe relative references.
- Create: `bugfix_automation/storage/repositories.py`
  - Provides small functions for config snapshots, Excel imports, operation events, AI sessions, and log indexes.
- Modify: `bugfix_automation/config.py`
  - Add derived `data_root` and `storage_db_path` config fields with YAML/env overrides.
- Modify: `bugfix_automation/application/excel_service.py`
  - Record Excel upload/import batch metadata and row snapshots.
- Modify: `bugfix_automation/runner.py`
  - Create operation records for `run-once` and `run-one`, create AI sessions, index AI log chunks.
- Modify: `bugfix_automation/task_state.py`
  - Keep current JSON behavior, also append operation history events to SQLite.
- Modify: `bugfix_automation/application/log_service.py`
  - Read AI logs by tail or byte range, not by loading one huge string.
- Modify: `bugfix_automation/api/routes/logs.py`
  - Add optional `offset` and `limit` query parameters.
- Test: `tests/test_storage.py`
  - Schema, migrations, repository writes, artifact metadata, log chunk indexing.
- Test: `tests/test_excel_storage.py`
  - Excel upload creates import batch and row snapshots.
- Test: `tests/test_ai_log_storage.py`
  - Large log is indexed and can be read in bounded chunks.

## Schema

Create `bugfix_automation/storage/schema.sql`:

```sql
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS config_snapshots (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  config_json TEXT NOT NULL,
  config_hash TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS excel_import_batches (
  id TEXT PRIMARY KEY,
  original_filename TEXT NOT NULL,
  stored_path TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  sheet_name TEXT NOT NULL,
  row_count INTEGER NOT NULL,
  status TEXT NOT NULL,
  config_snapshot_id TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY(config_snapshot_id) REFERENCES config_snapshots(id)
);

CREATE TABLE IF NOT EXISTS excel_import_rows (
  id TEXT PRIMARY KEY,
  batch_id TEXT NOT NULL,
  excel_row INTEGER NOT NULL,
  issue_id TEXT NOT NULL,
  row_json TEXT NOT NULL,
  description TEXT NOT NULL,
  assignee TEXT NOT NULL,
  requester_status TEXT NOT NULL,
  assignee_status TEXT NOT NULL,
  row_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(batch_id) REFERENCES excel_import_batches(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_excel_import_rows_batch_row
  ON excel_import_rows(batch_id, excel_row);

CREATE INDEX IF NOT EXISTS idx_excel_import_rows_issue
  ON excel_import_rows(issue_id);

CREATE TABLE IF NOT EXISTS operations (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  status TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  branch TEXT NOT NULL DEFAULT '',
  issue_id TEXT NOT NULL DEFAULT '',
  excel_row INTEGER,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  config_snapshot_id TEXT,
  excel_import_batch_id TEXT,
  summary TEXT NOT NULL DEFAULT '',
  FOREIGN KEY(config_snapshot_id) REFERENCES config_snapshots(id),
  FOREIGN KEY(excel_import_batch_id) REFERENCES excel_import_batches(id)
);

CREATE INDEX IF NOT EXISTS idx_operations_started
  ON operations(started_at DESC);

CREATE INDEX IF NOT EXISTS idx_operations_branch
  ON operations(branch);

CREATE TABLE IF NOT EXISTS operation_events (
  id TEXT PRIMARY KEY,
  operation_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT '',
  message TEXT NOT NULL DEFAULT '',
  payload_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  FOREIGN KEY(operation_id) REFERENCES operations(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_operation_events_operation_time
  ON operation_events(operation_id, created_at);

CREATE TABLE IF NOT EXISTS artifacts (
  id TEXT PRIMARY KEY,
  operation_id TEXT,
  artifact_type TEXT NOT NULL,
  path TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  mime_type TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  FOREIGN KEY(operation_id) REFERENCES operations(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_artifacts_operation
  ON artifacts(operation_id);

CREATE TABLE IF NOT EXISTS ai_sessions (
  id TEXT PRIMARY KEY,
  operation_id TEXT NOT NULL,
  provider TEXT NOT NULL,
  cli_tool TEXT NOT NULL,
  workspace_path TEXT NOT NULL,
  prompt_path TEXT NOT NULL,
  log_path TEXT NOT NULL,
  status TEXT NOT NULL,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  prompt_sha256 TEXT NOT NULL DEFAULT '',
  log_sha256 TEXT NOT NULL DEFAULT '',
  log_size_bytes INTEGER NOT NULL DEFAULT 0,
  summary_json TEXT NOT NULL DEFAULT '{}',
  FOREIGN KEY(operation_id) REFERENCES operations(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_ai_sessions_operation
  ON ai_sessions(operation_id);

CREATE TABLE IF NOT EXISTS ai_log_segments (
  id TEXT PRIMARY KEY,
  ai_session_id TEXT NOT NULL,
  seq INTEGER NOT NULL,
  offset_start INTEGER NOT NULL,
  offset_end INTEGER NOT NULL,
  line_start INTEGER NOT NULL,
  line_end INTEGER NOT NULL,
  preview TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  FOREIGN KEY(ai_session_id) REFERENCES ai_sessions(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_log_segments_session_seq
  ON ai_log_segments(ai_session_id, seq);
```

## Data Policy

- Current editable settings stay in `config.yaml`.
- Each user-triggered operation writes a `config_snapshots` row before it starts.
- Each Excel upload writes one `excel_import_batches` row and one `excel_import_rows` row per parsed worksheet row.
- Each user click or backend state transition writes one `operation_events` row.
- Each top-level action writes one `operations` row:
  - `excel_upload`
  - `run_once`
  - `run_one`
  - `approval_accept`
  - `approval_reject`
  - `rework`
  - `integration_create`
  - `integration_start`
  - `integration_commit`
- Long AI records are stored as `logs/ai/<ai_session_id>/full.log`; SQLite stores only metadata and 64 KiB segment indexes.
- API responses return at most a bounded log slice, defaulting to the last 120000 characters for compatibility.
- Retention can be simple: keep SQLite forever, keep full logs for 30 days or until manually deleted, keep summaries forever.

## Task 1: Add Storage Config

**Files:**
- Modify: `bugfix_automation/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Add this test to `tests/test_config.py`:

```python
def test_storage_paths_default_to_repo_data_dir(monkeypatch):
    monkeypatch.delenv("BUGFIX_DATA_ROOT", raising=False)
    monkeypatch.delenv("BUGFIX_STORAGE_DB_PATH", raising=False)

    config = load_config()

    assert config.data_root == repo_root_path() / "data"
    assert config.storage_db_path == repo_root_path() / "data" / "app.sqlite3"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_config.py::test_storage_paths_default_to_repo_data_dir -v`

Expected: FAIL with `AttributeError: 'Config' object has no attribute 'data_root'`.

- [ ] **Step 3: Add config fields**

In `bugfix_automation/config.py`, add these fields to `Config`:

```python
    data_root: Path = Path("data")
    storage_db_path: Path = Path("data/app.sqlite3")
```

Inside `load_config`, compute and pass:

```python
    data_root = _path(value("data_root", "BUGFIX_DATA_ROOT", repo_root / "data"), repo_root)
    storage_db_path = _path(value("storage_db_path", "BUGFIX_STORAGE_DB_PATH", data_root / "app.sqlite3"), repo_root)
```

And include in `Config(...)`:

```python
        data_root=data_root,
        storage_db_path=storage_db_path,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_config.py::test_storage_paths_default_to_repo_data_dir -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add bugfix_automation/config.py tests/test_config.py
git commit -m "feat: add storage config paths"
```

## Task 2: Create SQLite Schema and Migration Helper

**Files:**
- Create: `bugfix_automation/storage/__init__.py`
- Create: `bugfix_automation/storage/schema.sql`
- Create: `bugfix_automation/storage/db.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_storage.py`:

```python
from pathlib import Path
import sqlite3

from bugfix_automation.storage.db import connect, ensure_schema


def test_ensure_schema_creates_core_tables(tmp_path: Path):
    db_path = tmp_path / "app.sqlite3"

    ensure_schema(db_path)

    with sqlite3.connect(db_path) as db:
        names = {
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    assert "config_snapshots" in names
    assert "excel_import_batches" in names
    assert "excel_import_rows" in names
    assert "operations" in names
    assert "operation_events" in names
    assert "artifacts" in names
    assert "ai_sessions" in names
    assert "ai_log_segments" in names


def test_connect_uses_rows_and_foreign_keys(tmp_path: Path):
    db_path = tmp_path / "app.sqlite3"
    ensure_schema(db_path)

    with connect(db_path) as db:
        foreign_keys = db.execute("PRAGMA foreign_keys").fetchone()[0]
        journal_mode = db.execute("PRAGMA journal_mode").fetchone()[0]

    assert foreign_keys == 1
    assert journal_mode == "wal"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_storage.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'bugfix_automation.storage'`.

- [ ] **Step 3: Add schema and DB helper**

Create `bugfix_automation/storage/__init__.py`:

```python
from bugfix_automation.storage.db import connect, ensure_schema

__all__ = ["connect", "ensure_schema"]
```

Create `bugfix_automation/storage/schema.sql` using the SQL from the `Schema` section of this plan.

Create `bugfix_automation/storage/db.py`:

```python
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3


SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def ensure_schema(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as db:
        db.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        db.execute(
            "INSERT OR IGNORE INTO schema_migrations(version, applied_at) "
            "VALUES (1, datetime('now'))"
        )
        db.commit()


@contextmanager
def connect(db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA journal_mode = WAL")
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_storage.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add bugfix_automation/storage tests/test_storage.py
git commit -m "feat: add sqlite storage schema"
```

## Task 3: Add Repository Functions

**Files:**
- Create: `bugfix_automation/storage/repositories.py`
- Modify: `tests/test_storage.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_storage.py`:

```python
from bugfix_automation.storage.repositories import (
    append_operation_event,
    create_operation,
    save_config_snapshot,
)


def test_repositories_save_snapshot_operation_and_event(tmp_path: Path):
    db_path = tmp_path / "app.sqlite3"
    ensure_schema(db_path)

    snapshot_id = save_config_snapshot(
        db_path,
        source="test",
        config={"active_workspace": "pc-web", "max_concurrency": 2},
    )
    operation_id = create_operation(
        db_path,
        kind="run_one",
        workspace_id="pc-web",
        status="running",
        branch="fix/demo",
        issue_id="42",
        excel_row=88,
        config_snapshot_id=snapshot_id,
        excel_import_batch_id=None,
        summary="manual run for one Excel row",
    )
    event_id = append_operation_event(
        db_path,
        operation_id=operation_id,
        event_type="state",
        status="running",
        message="AI started",
        payload={"phase": "codex"},
    )

    with connect(db_path) as db:
        snapshot = db.execute("SELECT * FROM config_snapshots").fetchone()
        operation = db.execute("SELECT * FROM operations").fetchone()
        event = db.execute("SELECT * FROM operation_events").fetchone()

    assert snapshot["id"] == snapshot_id
    assert operation["id"] == operation_id
    assert operation["branch"] == "fix/demo"
    assert event["id"] == event_id
    assert event["operation_id"] == operation_id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_storage.py::test_repositories_save_snapshot_operation_and_event -v`

Expected: FAIL with `ModuleNotFoundError` or import error for repository functions.

- [ ] **Step 3: Implement repository functions**

Create `bugfix_automation/storage/repositories.py`:

```python
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from bugfix_automation.storage.db import connect, ensure_schema


def utc_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def stable_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def save_config_snapshot(db_path: Path, source: str, config: dict[str, Any]) -> str:
    ensure_schema(db_path)
    snapshot_json = stable_json(config)
    snapshot_id = new_id("cfg")
    with connect(db_path) as db:
        db.execute(
            "INSERT INTO config_snapshots(id, source, config_json, config_hash, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (snapshot_id, source, snapshot_json, sha256_text(snapshot_json), utc_now()),
        )
        db.commit()
    return snapshot_id


def create_operation(
    db_path: Path,
    *,
    kind: str,
    workspace_id: str,
    status: str,
    branch: str = "",
    issue_id: str = "",
    excel_row: int | None = None,
    config_snapshot_id: str | None = None,
    excel_import_batch_id: str | None = None,
    summary: str = "",
) -> str:
    ensure_schema(db_path)
    operation_id = new_id("op")
    with connect(db_path) as db:
        db.execute(
            "INSERT INTO operations("
            "id, kind, status, workspace_id, branch, issue_id, excel_row, started_at, "
            "config_snapshot_id, excel_import_batch_id, summary"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                operation_id,
                kind,
                status,
                workspace_id,
                branch,
                issue_id,
                excel_row,
                utc_now(),
                config_snapshot_id,
                excel_import_batch_id,
                summary,
            ),
        )
        db.commit()
    return operation_id


def append_operation_event(
    db_path: Path,
    *,
    operation_id: str,
    event_type: str,
    status: str = "",
    message: str = "",
    payload: dict[str, Any] | None = None,
) -> str:
    ensure_schema(db_path)
    event_id = new_id("evt")
    payload_json = stable_json(payload or {})
    with connect(db_path) as db:
        db.execute(
            "INSERT INTO operation_events(id, operation_id, event_type, status, message, payload_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (event_id, operation_id, event_type, status, message, payload_json, utc_now()),
        )
        db.commit()
    return event_id
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_storage.py::test_repositories_save_snapshot_operation_and_event -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add bugfix_automation/storage/repositories.py tests/test_storage.py
git commit -m "feat: add storage repositories"
```

## Task 4: Record Excel Imports

**Files:**
- Modify: `bugfix_automation/storage/repositories.py`
- Modify: `bugfix_automation/application/excel_service.py`
- Create: `tests/test_excel_storage.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_excel_storage.py`:

```python
from pathlib import Path
import sqlite3

from bugfix_automation.config import load_config
from bugfix_automation.storage.db import ensure_schema
from bugfix_automation.storage.repositories import save_excel_import


def test_save_excel_import_persists_batch_and_rows(tmp_path: Path):
    db_path = tmp_path / "app.sqlite3"
    ensure_schema(db_path)
    excel_path = tmp_path / "bugs.xlsx"
    excel_path.write_bytes(b"fake-xlsx-bytes")

    batch_id = save_excel_import(
        db_path,
        original_filename="bugs.xlsx",
        stored_path=excel_path,
        sheet_name="在线问题清单",
        rows=[
            {
                "_excel_row": "46",
                "序号": "1",
                "问题描述": "上传附件反馈不明显",
                "对接人": "谢浩杰",
                "提出人状态": "待处理",
                "对接人状态": "处理中",
            }
        ],
        config_snapshot_id=None,
    )

    with sqlite3.connect(db_path) as db:
        batch_count = db.execute("SELECT COUNT(*) FROM excel_import_batches").fetchone()[0]
        row = db.execute("SELECT issue_id, excel_row, description FROM excel_import_rows").fetchone()

    assert batch_count == 1
    assert batch_id.startswith("xls_")
    assert row == ("1", 46, "上传附件反馈不明显")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_excel_storage.py -v`

Expected: FAIL with import error for `save_excel_import`.

- [ ] **Step 3: Add Excel repository function**

Add to `bugfix_automation/storage/repositories.py`:

```python
import hashlib


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save_excel_import(
    db_path: Path,
    *,
    original_filename: str,
    stored_path: Path,
    sheet_name: str,
    rows: list[dict[str, Any]],
    config_snapshot_id: str | None,
) -> str:
    ensure_schema(db_path)
    batch_id = new_id("xls")
    now = utc_now()
    with connect(db_path) as db:
        db.execute(
            "INSERT INTO excel_import_batches("
            "id, original_filename, stored_path, sha256, sheet_name, row_count, status, config_snapshot_id, created_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                batch_id,
                original_filename,
                str(stored_path),
                sha256_file(stored_path),
                sheet_name,
                len(rows),
                "imported",
                config_snapshot_id,
                now,
            ),
        )
        for row in rows:
            row_json = stable_json(row)
            excel_row = int(row.get("_excel_row") or 0)
            issue_id = str(row.get("序号") or "")
            description = str(row.get("问题描述") or "")
            db.execute(
                "INSERT INTO excel_import_rows("
                "id, batch_id, excel_row, issue_id, row_json, description, assignee, "
                "requester_status, assignee_status, row_hash, created_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    new_id("row"),
                    batch_id,
                    excel_row,
                    issue_id,
                    row_json,
                    description,
                    str(row.get("对接人") or ""),
                    str(row.get("提出人状态") or ""),
                    str(row.get("对接人状态") or ""),
                    sha256_text(row_json),
                    now,
                ),
            )
        db.commit()
    return batch_id
```

- [ ] **Step 4: Wire Excel upload**

In `bugfix_automation/application/excel_service.py`, after `update_config_yaml({"excel_path": target})`, add:

```python
    config = load_config()
    rows = read_sheet(target, config.sheet_name)
    save_excel_import(
        config.storage_db_path,
        original_filename=original_name,
        stored_path=target,
        sheet_name=config.sheet_name,
        rows=rows,
        config_snapshot_id=None,
    )
```

And import:

```python
from bugfix_automation.storage.repositories import save_excel_import
```

- [ ] **Step 5: Run tests**

Run: `python3 -m pytest tests/test_excel_storage.py tests/test_excel_reader.py tests/test_fastapi_api.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add bugfix_automation/application/excel_service.py bugfix_automation/storage/repositories.py tests/test_excel_storage.py
git commit -m "feat: record excel imports in storage"
```

## Task 5: Record Operation History

**Files:**
- Modify: `bugfix_automation/task_state.py`
- Modify: `bugfix_automation/runner.py`
- Modify: `bugfix_automation/storage/repositories.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_storage.py`:

```python
from bugfix_automation.storage.repositories import finish_operation, list_operation_events


def test_operation_can_be_finished_and_events_listed(tmp_path: Path):
    db_path = tmp_path / "app.sqlite3"
    ensure_schema(db_path)
    operation_id = create_operation(
        db_path,
        kind="run_once",
        workspace_id="pc-web",
        status="running",
        summary="nightly run",
    )
    append_operation_event(
        db_path,
        operation_id=operation_id,
        event_type="state",
        status="running",
        message="queued",
        payload={"phase": "queued"},
    )
    finish_operation(db_path, operation_id=operation_id, status="succeeded", summary="1 fix pending approval")

    events = list_operation_events(db_path, operation_id)

    with connect(db_path) as db:
        operation = db.execute("SELECT status, ended_at, summary FROM operations WHERE id = ?", (operation_id,)).fetchone()

    assert operation["status"] == "succeeded"
    assert operation["ended_at"]
    assert operation["summary"] == "1 fix pending approval"
    assert events[0]["message"] == "queued"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_storage.py::test_operation_can_be_finished_and_events_listed -v`

Expected: FAIL with import error for `finish_operation`.

- [ ] **Step 3: Add operation helpers**

Add to `bugfix_automation/storage/repositories.py`:

```python
def finish_operation(db_path: Path, *, operation_id: str, status: str, summary: str = "") -> None:
    ensure_schema(db_path)
    with connect(db_path) as db:
        db.execute(
            "UPDATE operations SET status = ?, ended_at = ?, summary = ? WHERE id = ?",
            (status, utc_now(), summary, operation_id),
        )
        db.commit()


def list_operation_events(db_path: Path, operation_id: str) -> list[dict[str, Any]]:
    ensure_schema(db_path)
    with connect(db_path) as db:
        rows = db.execute(
            "SELECT * FROM operation_events WHERE operation_id = ? ORDER BY created_at ASC",
            (operation_id,),
        ).fetchall()
    return [dict(row) for row in rows]
```

- [ ] **Step 4: Wire state transitions**

Keep `task-state.json` exactly as it works now. Add an optional SQLite append inside `set_task_state`:

```python
        operation_id = str(next_state.get("operation_id") or "")
        if operation_id:
            append_operation_event(
                config.storage_db_path,
                operation_id=operation_id,
                event_type="task_state",
                status=status,
                message=detail,
                payload={"branch": branch, "phase": phase, "pid": next_state.get("pid")},
            )
```

Import:

```python
from bugfix_automation.storage.repositories import append_operation_event
```

- [ ] **Step 5: Run tests**

Run: `python3 -m pytest tests/test_storage.py tests/test_approval.py tests/test_scheduler.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add bugfix_automation/task_state.py bugfix_automation/runner.py bugfix_automation/storage/repositories.py tests/test_storage.py
git commit -m "feat: record operation history"
```

## Task 6: Store AI Logs as Files with Segment Indexes

**Files:**
- Modify: `bugfix_automation/storage/repositories.py`
- Modify: `bugfix_automation/runner.py`
- Modify: `bugfix_automation/application/log_service.py`
- Create: `tests/test_ai_log_storage.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_ai_log_storage.py`:

```python
from pathlib import Path

from bugfix_automation.storage.db import ensure_schema
from bugfix_automation.storage.repositories import (
    create_ai_session,
    index_ai_log_segments,
    read_ai_log_slice,
)


def test_ai_log_is_indexed_and_read_by_slice(tmp_path: Path):
    db_path = tmp_path / "app.sqlite3"
    ensure_schema(db_path)
    operation_id = "op_test"
    with open(tmp_path / "seed.sql", "w", encoding="utf-8") as file:
        file.write("")
    log_dir = tmp_path / "logs" / "ai" / "session"
    log_dir.mkdir(parents=True)
    prompt_path = log_dir / "prompt.txt"
    log_path = log_dir / "full.log"
    prompt_path.write_text("fix bug", encoding="utf-8")
    log_path.write_text("line-1\n" + ("x" * 70000) + "\nline-3\n", encoding="utf-8")

    with connect(db_path) as db:
        db.execute(
            "INSERT INTO operations(id, kind, status, workspace_id, started_at) VALUES (?, ?, ?, ?, ?)",
            (operation_id, "run_one", "running", "pc-web", "2026-05-20T10:00:00"),
        )
        db.commit()

    session_id = create_ai_session(
        db_path,
        operation_id=operation_id,
        provider="local-cli",
        cli_tool="codex",
        workspace_path=tmp_path,
        prompt_path=prompt_path,
        log_path=log_path,
    )
    index_ai_log_segments(db_path, ai_session_id=session_id, log_path=log_path, segment_size=65536)

    first = read_ai_log_slice(log_path, offset=0, limit=20)
    later = read_ai_log_slice(log_path, offset=65536, limit=20)

    assert first["content"].startswith("line-1")
    assert first["next_offset"] == 20
    assert len(later["content"]) == 20
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_ai_log_storage.py -v`

Expected: FAIL with import errors for AI log repository functions.

- [ ] **Step 3: Add AI session helpers**

Add to `bugfix_automation/storage/repositories.py`:

```python
def create_ai_session(
    db_path: Path,
    *,
    operation_id: str,
    provider: str,
    cli_tool: str,
    workspace_path: Path,
    prompt_path: Path,
    log_path: Path,
) -> str:
    ensure_schema(db_path)
    session_id = new_id("ai")
    with connect(db_path) as db:
        db.execute(
            "INSERT INTO ai_sessions("
            "id, operation_id, provider, cli_tool, workspace_path, prompt_path, log_path, status, started_at, prompt_sha256"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                operation_id,
                provider,
                cli_tool,
                str(workspace_path),
                str(prompt_path),
                str(log_path),
                "running",
                utc_now(),
                sha256_file(prompt_path) if prompt_path.exists() else "",
            ),
        )
        db.commit()
    return session_id


def finish_ai_session(db_path: Path, *, ai_session_id: str, status: str, log_path: Path, summary: dict[str, Any]) -> None:
    ensure_schema(db_path)
    with connect(db_path) as db:
        db.execute(
            "UPDATE ai_sessions SET status = ?, ended_at = ?, log_sha256 = ?, log_size_bytes = ?, summary_json = ? WHERE id = ?",
            (
                status,
                utc_now(),
                sha256_file(log_path) if log_path.exists() else "",
                log_path.stat().st_size if log_path.exists() else 0,
                stable_json(summary),
                ai_session_id,
            ),
        )
        db.commit()


def index_ai_log_segments(
    db_path: Path,
    *,
    ai_session_id: str,
    log_path: Path,
    segment_size: int = 65536,
) -> None:
    ensure_schema(db_path)
    data = log_path.read_bytes() if log_path.exists() else b""
    now = utc_now()
    with connect(db_path) as db:
        db.execute("DELETE FROM ai_log_segments WHERE ai_session_id = ?", (ai_session_id,))
        line_start = 1
        for seq, offset_start in enumerate(range(0, len(data), segment_size), start=1):
            chunk = data[offset_start : offset_start + segment_size]
            offset_end = offset_start + len(chunk)
            text = chunk.decode("utf-8", errors="replace")
            newline_count = text.count("\n")
            line_end = line_start + newline_count
            preview = text[:240]
            db.execute(
                "INSERT INTO ai_log_segments("
                "id, ai_session_id, seq, offset_start, offset_end, line_start, line_end, preview, created_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    new_id("seg"),
                    ai_session_id,
                    seq,
                    offset_start,
                    offset_end,
                    line_start,
                    line_end,
                    preview,
                    now,
                ),
            )
            line_start = line_end + 1
        db.commit()


def read_ai_log_slice(log_path: Path, *, offset: int, limit: int) -> dict[str, Any]:
    safe_offset = max(0, offset)
    safe_limit = max(1, min(limit, 200000))
    if not log_path.exists():
        return {"offset": safe_offset, "next_offset": safe_offset, "content": "", "size": 0}
    size = log_path.stat().st_size
    with log_path.open("rb") as file:
        file.seek(min(safe_offset, size))
        data = file.read(safe_limit)
    content = data.decode("utf-8", errors="replace")
    return {
        "offset": safe_offset,
        "next_offset": min(safe_offset + len(data), size),
        "content": content,
        "size": size,
    }
```

- [ ] **Step 4: Wire AI log writing**

In `runner.py`, keep writing the existing log file for backward compatibility. When an operation id is available, write:

```python
ai_dir = config.logs_root / "ai" / ai_session_id
prompt_path = ai_dir / "prompt.txt"
log_path = ai_dir / "full.log"
ai_dir.mkdir(parents=True, exist_ok=True)
prompt_path.write_text(prompt, encoding="utf-8")
```

Pass `log_path` to `_run(...)`. After the AI command finishes or fails:

```python
index_ai_log_segments(config.storage_db_path, ai_session_id=ai_session_id, log_path=log_path)
finish_ai_session(
    config.storage_db_path,
    ai_session_id=ai_session_id,
    status="succeeded",
    log_path=log_path,
    summary={"branch": branch, "issue_id": bug.issue_id, "excel_row": bug.excel_row},
)
```

- [ ] **Step 5: Update log service**

In `bugfix_automation/application/log_service.py`, replace full-file loading with bounded reading:

```python
def log_payload(config: Config, branch: str, offset: int | None = None, limit: int = 120000) -> dict[str, Any]:
    if not branch:
        return {"branch": "", "path": "", "content": "", "offset": 0, "next_offset": 0, "size": 0}
    path = codex_log_path(config, branch)
    if not path.exists():
        return {"branch": branch, "path": str(path), "content": "", "offset": 0, "next_offset": 0, "size": 0}
    size = path.stat().st_size
    start = max(0, size - limit) if offset is None else max(0, offset)
    payload = read_ai_log_slice(path, offset=start, limit=limit)
    return {"branch": branch, "path": str(path), **payload}
```

- [ ] **Step 6: Run tests**

Run: `python3 -m pytest tests/test_ai_log_storage.py tests/test_fastapi_api.py tests/test_approval.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add bugfix_automation/runner.py bugfix_automation/application/log_service.py bugfix_automation/storage/repositories.py tests/test_ai_log_storage.py
git commit -m "feat: store ai logs as indexed files"
```

## Task 7: Add Query APIs for History

**Files:**
- Modify: `bugfix_automation/api/schemas.py`
- Create: `bugfix_automation/application/history_service.py`
- Create: `bugfix_automation/api/routes/history.py`
- Modify: `bugfix_automation/api/app.py`
- Test: `tests/test_fastapi_api.py`

- [ ] **Step 1: Write the failing API test**

Add to `tests/test_fastapi_api.py`:

```python
def test_history_endpoint_returns_operations(api_client):
    response = api_client.get("/api/history/operations")

    assert response.status_code == 200
    payload = response.json()
    assert "items" in payload
    assert isinstance(payload["items"], list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_fastapi_api.py::test_history_endpoint_returns_operations -v`

Expected: FAIL with 404.

- [ ] **Step 3: Implement history service**

Create `bugfix_automation/application/history_service.py`:

```python
from __future__ import annotations

from typing import Any

from bugfix_automation.config import Config
from bugfix_automation.storage.db import connect, ensure_schema


def list_operations(config: Config, limit: int = 100) -> dict[str, Any]:
    ensure_schema(config.storage_db_path)
    safe_limit = max(1, min(limit, 500))
    with connect(config.storage_db_path) as db:
        rows = db.execute(
            "SELECT * FROM operations ORDER BY started_at DESC LIMIT ?",
            (safe_limit,),
        ).fetchall()
    return {"items": [dict(row) for row in rows]}
```

Create `bugfix_automation/api/routes/history.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Query

from bugfix_automation.application.history_service import list_operations
from bugfix_automation.config import load_config


router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("/operations")
def operations(limit: int = Query(default=100, ge=1, le=500)):
    return list_operations(load_config(), limit=limit)
```

In `bugfix_automation/api/app.py`, include the router:

```python
from bugfix_automation.api.routes import history
```

And:

```python
app.include_router(history.router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_fastapi_api.py::test_history_endpoint_returns_operations -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add bugfix_automation/application/history_service.py bugfix_automation/api/routes/history.py bugfix_automation/api/app.py tests/test_fastapi_api.py
git commit -m "feat: expose operation history api"
```

## Self-Review

Spec coverage:

- 配置信息: covered by `config.yaml` plus `config_snapshots`.
- 用户导入 Excel 记录: covered by `excel_import_batches` and `excel_import_rows`.
- 用户执行操作记录: covered by `operations`.
- 操作历史记录: covered by append-only `operation_events`.
- AI 执行长记录: covered by file-backed `logs/ai/<session>/full.log`, `ai_sessions`, and `ai_log_segments`.

Placeholder scan:

- The plan contains concrete paths, schema, commands, and expected test results.
- There are no deferred implementation markers.

Type consistency:

- IDs use string prefixes: `cfg_`, `xls_`, `row_`, `op_`, `evt_`, `ai_`, `seg_`.
- Repository functions consistently accept `db_path: Path`.
- Log slice responses consistently expose `offset`, `next_offset`, `content`, and `size`.
