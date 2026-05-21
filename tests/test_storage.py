from pathlib import Path
import sqlite3

from bugfix_automation.storage.db import connect, ensure_schema
from bugfix_automation.storage.repositories import (
    append_operation_event,
    create_operation,
    finish_operation,
    list_operation_events,
    save_config_snapshot,
)


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
        row = db.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
        foreign_keys = db.execute("PRAGMA foreign_keys").fetchone()[0]
        journal_mode = db.execute("PRAGMA journal_mode").fetchone()[0]

    assert row["name"]
    assert foreign_keys == 1
    assert journal_mode == "wal"


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
