from pathlib import Path
import sqlite3

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
