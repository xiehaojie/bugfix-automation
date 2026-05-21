from pathlib import Path
import tempfile

from bugfix_automation.application.excel_adapter_service import save_excel_adapter, sanitize_adapter_suggestion
from bugfix_automation.config import Config
from bugfix_automation.storage.settings import get_setting
from tests.test_excel_reader import write_minimal_xlsx


def test_sanitize_adapter_suggestion_drops_unknown_headers() -> None:
    suggestion = {
        "canonical_fields": {"issue_id": "编号", "description": "不存在"},
        "prompt": {"fields": ["标题", "不存在"], "template": "专用模板"},
        "branch_summary_fields": ["标题", "不存在"],
        "filters": [
            {"field": "状态", "op": "not_in", "values": ["已解决"]},
            {"field": "不存在", "op": "equals", "value": "x"},
        ],
        "warnings": [],
    }

    cleaned = sanitize_adapter_suggestion(suggestion, headers=["编号", "标题", "状态"])

    assert cleaned["canonical_fields"] == {"issue_id": "编号"}
    assert cleaned["prompt"]["fields"] == ["标题"]
    assert cleaned["branch_summary_fields"] == ["标题"]
    assert cleaned["filters"] == [{"field": "状态", "op": "not_in", "values": ["已解决"]}]
    assert cleaned["warnings"]


def test_sanitize_adapter_suggestion_requires_description_on_save() -> None:
    suggestion = {"canonical_fields": {"issue_id": "编号"}, "prompt": {"fields": ["标题"]}}

    try:
        sanitize_adapter_suggestion(suggestion, headers=["编号", "标题"], require_description=True)
    except ValueError as exc:
        assert "description" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_save_excel_adapter_writes_runtime_settings() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        workbook = root / "bugs.xlsx"
        write_minimal_xlsx(workbook)
        config = Config(
            excel_path=workbook,
            sheet_name="在线问题清单",
            assignee="谢浩杰",
            target_repo=root / "repo",
            target_app_path="apps/pc-web",
            worktree_root=root / "worktrees",
            runs_root=root / "runs",
            logs_root=root / "logs",
            launchd_label="local.test",
            cli_tool="codex",
            schedule_hour=22,
            schedule_minute=0,
            approval_web_port=8765,
            approval_api_port=8766,
            data_root=root / "data",
            storage_db_path=root / "data" / "app.sqlite3",
            prompt_context_paths=("apps/pc-web/src",),
        )
        adapter = {
            "canonical_fields": {"issue_id": "序号", "description": "问题描述"},
            "prompt": {"fields": ["问题描述", "不存在"], "template": "专用模板"},
            "branch_summary_fields": ["问题描述"],
            "filters": [
                {"field": "提出人状态", "op": "not_in", "values": ["已解决"]},
                {"field": "不存在", "op": "equals", "value": "x"},
            ],
        }

        response = save_excel_adapter(config, adapter)

        assert response["ok"] is True
        assert get_setting(config.storage_db_path, "excel_profile") == {
            "canonical_fields": {"issue_id": "序号", "description": "问题描述"},
            "prompt": {
                "fields": ["问题描述"],
                "template": "专用模板",
                "branch_summary_fields": ["问题描述"],
            },
        }
        assert get_setting(config.storage_db_path, "prompt") == {
            "fields": ["问题描述"],
            "template": "专用模板",
            "context_paths": ["apps/pc-web/src"],
        }
        assert get_setting(config.storage_db_path, "branch_summary_fields") == ["问题描述"]
        assert get_setting(config.storage_db_path, "filters") == [
            {"field": "提出人状态", "op": "not_in", "values": ["已解决"]}
        ]
