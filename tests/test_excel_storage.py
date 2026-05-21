from pathlib import Path
import sqlite3

from bugfix_automation.config import CanonicalFieldMapping
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


def test_save_excel_import_uses_canonical_mapping(tmp_path: Path):
    db_path = tmp_path / "app.sqlite3"
    excel_path = tmp_path / "bugs.xlsx"
    excel_path.write_bytes(b"fake-xlsx-bytes")

    save_excel_import(
        db_path,
        original_filename="bugs.xlsx",
        stored_path=excel_path,
        sheet_name="Sheet1",
        rows=[
            {
                "_excel_row": "5",
                "编号": "A-5",
                "标题": "按钮错位",
                "负责人": "谢浩杰",
                "提出状态": "待处理",
                "状态": "处理中",
            }
        ],
        config_snapshot_id=None,
        mapping=CanonicalFieldMapping(
            issue_id="编号",
            description="标题",
            assignee="负责人",
            requester_status="提出状态",
            assignee_status="状态",
        ),
    )

    with sqlite3.connect(db_path) as db:
        row = db.execute(
            "SELECT issue_id, description, assignee, requester_status, assignee_status FROM excel_import_rows"
        ).fetchone()

    assert row == ("A-5", "按钮错位", "谢浩杰", "待处理", "处理中")
