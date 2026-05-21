from pathlib import Path

from bugfix_automation.storage.db import connect, ensure_schema
from bugfix_automation.storage.repositories import (
    create_ai_session,
    index_ai_log_segments,
    read_ai_log_slice,
)


def test_ai_log_is_indexed_and_read_by_slice(tmp_path: Path):
    db_path = tmp_path / "app.sqlite3"
    ensure_schema(db_path)
    operation_id = "op_test"
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
