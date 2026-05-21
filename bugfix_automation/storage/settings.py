from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bugfix_automation.storage.db import connect, ensure_schema
from bugfix_automation.storage.repositories import utc_now


def get_settings(db_path: Path) -> dict[str, Any]:
    ensure_schema(db_path)
    with connect(db_path) as db:
        rows = db.execute("SELECT key, value_json FROM app_settings").fetchall()
    settings: dict[str, Any] = {}
    for row in rows:
        try:
            settings[str(row["key"])] = json.loads(str(row["value_json"]))
        except json.JSONDecodeError:
            settings[str(row["key"])] = None
    return settings


def get_setting(db_path: Path, key: str, default: Any = None) -> Any:
    ensure_schema(db_path)
    with connect(db_path) as db:
        row = db.execute("SELECT value_json FROM app_settings WHERE key = ?", (key,)).fetchone()
    if row is None:
        return default
    try:
        return json.loads(str(row["value_json"]))
    except json.JSONDecodeError:
        return default


def set_setting(db_path: Path, key: str, value: Any) -> None:
    ensure_schema(db_path)
    with connect(db_path) as db:
        db.execute(
            "INSERT INTO app_settings(key, value_json, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json, updated_at = excluded.updated_at",
            (key, json.dumps(value, ensure_ascii=False, sort_keys=True), utc_now()),
        )
        db.commit()
