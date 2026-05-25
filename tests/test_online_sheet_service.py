from __future__ import annotations

from pathlib import Path

import pytest

from bugfix_automation.application import online_sheet_service
from bugfix_automation.config import Config
from bugfix_automation.excel_reader import read_sheet
from bugfix_automation.integrations.online_sheets.base import SheetRef, SheetTable
from bugfix_automation.integrations.online_sheets.tencent_docs import TencentDocsSheetProvider
from bugfix_automation.integrations.online_sheets.wps import WpsSheetProvider
from bugfix_automation.integrations.online_sheets.registry import provider_keys
from bugfix_automation.storage.settings import get_setting


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config(
        excel_path=tmp_path / "bugs.xlsx",
        sheet_name="在线问题清单",
        assignee="谢浩杰",
        target_repo=tmp_path / "repo",
        target_app_path="apps/pc-web",
        worktree_root=tmp_path / "worktrees",
        runs_root=tmp_path / "runs",
        logs_root=tmp_path / "logs",
        data_root=tmp_path / "data",
        storage_db_path=tmp_path / "data" / "app.sqlite3",
        launchd_label="local.test",
        cli_tool="codex",
        schedule_hour=22,
        schedule_minute=0,
        approval_web_port=8765,
        approval_api_port=8766,
    )


class FakeProvider:
    key = "fake"
    label = "Fake Sheet"

    def parse_url(self, url: str) -> SheetRef:
        return SheetRef(provider=self.key, source_url=url, workbook_id="book-1", sheet_id="sheet-1")

    def read_range(self, ref: SheetRef, range_address: str) -> SheetTable:
        return SheetTable(
            ref=ref,
            range_address=range_address,
            headers=["序号", "问题描述", "对接人状态"],
            rows=[
                {"序号": "1", "问题描述": "按钮无反馈", "对接人状态": "处理中"},
                {"序号": "2", "问题描述": "下载无提示", "对接人状态": ""},
            ],
        )


def test_registry_exposes_four_online_sheet_providers():
    assert set(provider_keys()) >= {"feishu", "dingtalk", "tencent_docs", "wps"}


def test_preview_online_sheet_returns_headers_and_sample_rows(config: Config):
    provider = FakeProvider()

    result = online_sheet_service.preview_online_sheet(
        config,
        provider_key="fake",
        url="https://example.test/sheet",
        range_address="A1:C100",
        provider=provider,
    )

    assert result["ok"] is True
    assert result["provider"] == "fake"
    assert result["headers"] == ["序号", "问题描述", "对接人状态"]
    assert result["row_count"] == 2
    assert result["rows"][0]["问题描述"] == "按钮无反馈"


def test_preview_online_sheet_rejects_oversized_range(config: Config):
    provider = FakeProvider()

    with pytest.raises(RuntimeError, match="读取范围过大"):
        online_sheet_service.preview_online_sheet(
            config,
            provider_key="fake",
            url="https://example.test/sheet",
            range_address="A1:XFD1048576",
            provider=provider,
        )


def test_import_online_sheet_writes_xlsx_and_updates_excel_setting(config: Config, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    provider = FakeProvider()
    monkeypatch.setattr(online_sheet_service, "repo_root_path", lambda: tmp_path)

    result = online_sheet_service.import_online_sheet(
        config,
        provider_key="fake",
        url="https://example.test/sheet",
        range_address="A1:C100",
        provider=provider,
    )

    assert result["ok"] is True
    imported_path = Path(result["excel_path"])
    assert imported_path.exists()
    assert imported_path.suffix == ".xlsx"
    assert get_setting(config.storage_db_path, "excel") == {
        "excel_path": str(imported_path),
        "sheet_name": config.sheet_name,
        "online_sheet": {
            "provider": "fake",
            "source_url": "https://example.test/sheet",
            "workbook_id": "book-1",
            "sheet_id": "sheet-1",
            "range": "A1:C100",
        },
    }
    rows = read_sheet(imported_path, config.sheet_name)
    assert rows[0]["序号"] == "1"
    assert rows[1]["问题描述"] == "下载无提示"


def test_tencent_docs_template_encodes_range(monkeypatch: pytest.MonkeyPatch):
    seen: dict[str, str] = {}
    monkeypatch.setenv("TENCENT_DOCS_READ_URL_TEMPLATE", "https://example.test/{workbook_id}/{sheet_id}?range={range}")
    monkeypatch.setenv("TENCENT_DOCS_ACCESS_TOKEN", "token")
    monkeypatch.setenv("TENCENT_DOCS_CLIENT_ID", "client")
    monkeypatch.setenv("TENCENT_DOCS_OPEN_ID", "open")

    def fake_get_json(url: str, headers: dict[str, str] | None = None):
        seen["url"] = url
        return {"values": [["序号"], ["1"]]}

    monkeypatch.setattr("bugfix_automation.integrations.online_sheets.tencent_docs.get_json", fake_get_json)

    provider = TencentDocsSheetProvider()
    provider.read_range(
        SheetRef(provider="tencent_docs", source_url="https://docs.qq.com/sheet/book-1", workbook_id="book-1", sheet_id="sheet-1"),
        "A1:Z10&foo=bar",
    )

    assert seen["url"].endswith("?range=A1%3AZ10%26foo%3Dbar")


def test_tencent_docs_mcp_reads_markdown_table(monkeypatch: pytest.MonkeyPatch):
    seen: dict[str, object] = {}
    monkeypatch.delenv("TENCENT_DOCS_READ_URL_TEMPLATE", raising=False)
    monkeypatch.setenv("TENCENT_DOCS_TOKEN", "Bearer token")
    monkeypatch.setenv("TENCENT_DOCS_MCP_URL", "https://docs.qq.com/openapi/mcp")
    monkeypatch.setenv("TENCENT_DOCS_MCP_ARGUMENTS_TEMPLATE", '{"url":"{source_url}","range":"{range}"}')

    def fake_post_json(url: str, payload: dict, headers: dict[str, str] | None = None):
        seen["url"] = url
        seen["payload"] = payload
        seen["headers"] = headers
        return {
            "jsonrpc": "2.0",
            "id": payload["id"],
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": "| 序号 | 问题描述 |\n| --- | --- |\n| 1 | 按钮无反馈 |",
                    }
                ]
            },
        }

    monkeypatch.setattr("bugfix_automation.integrations.online_sheets.tencent_docs.post_json", fake_post_json)

    provider = TencentDocsSheetProvider()
    table = provider.read_range(
        SheetRef(provider="tencent_docs", source_url="https://docs.qq.com/sheet/book-1", workbook_id="book-1", sheet_id="sheet-1"),
        "A1:B10",
    )

    assert seen["url"] == "https://docs.qq.com/openapi/mcp"
    assert seen["headers"]["Authorization"] == "Bearer token"  # type: ignore[index]
    assert seen["payload"]["method"] == "tools/call"  # type: ignore[index]
    assert seen["payload"]["params"]["arguments"] == {"url": "https://docs.qq.com/sheet/book-1", "range": "A1:B10"}  # type: ignore[index]
    assert table.headers == ["序号", "问题描述"]
    assert table.rows == [{"序号": "1", "问题描述": "按钮无反馈"}]


def test_tencent_docs_reads_mcp_credentials_from_config_yaml(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
online_sheets:
  tencent_docs:
    token: Bearer yaml-token
    mcp_url: https://docs.qq.com/openapi/mcp
    mcp_tool: get_content
    mcp_arguments_template: '{"url":"{source_url}","range":"{range}"}'
""",
        encoding="utf-8",
    )
    for name in ("TENCENT_DOCS_TOKEN", "TENCENT_DOCS_MCP_URL", "TENCENT_DOCS_MCP_TOOL", "TENCENT_DOCS_MCP_ARGUMENTS_TEMPLATE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("BUGFIX_CONFIG_PATH", str(config_path))
    seen: dict[str, object] = {}

    def fake_post_json(url: str, payload: dict, headers: dict[str, str] | None = None):
        seen["url"] = url
        seen["payload"] = payload
        seen["headers"] = headers
        return {"result": {"values": [["序号"], ["1"]]}}

    monkeypatch.setattr("bugfix_automation.integrations.online_sheets.tencent_docs.post_json", fake_post_json)

    provider = TencentDocsSheetProvider()
    table = provider.read_range(
        SheetRef(provider="tencent_docs", source_url="https://docs.qq.com/sheet/book-1", workbook_id="book-1", sheet_id="sheet-1"),
        "A1:A2",
    )

    assert seen["url"] == "https://docs.qq.com/openapi/mcp"
    assert seen["headers"]["Authorization"] == "Bearer yaml-token"  # type: ignore[index]
    assert seen["payload"]["params"]["name"] == "get_content"  # type: ignore[index]
    assert table.rows == [{"序号": "1"}]


def test_wps_template_encodes_range(monkeypatch: pytest.MonkeyPatch):
    seen: dict[str, str] = {}
    monkeypatch.setenv("WPS_READ_URL_TEMPLATE", "https://example.test/{workbook_id}/{sheet_id}?range={range}")
    monkeypatch.setenv("WPS_ACCESS_TOKEN", "token")

    def fake_get_json(url: str, headers: dict[str, str] | None = None):
        seen["url"] = url
        return {"values": [["序号"], ["1"]]}

    monkeypatch.setattr("bugfix_automation.integrations.online_sheets.wps.get_json", fake_get_json)

    provider = WpsSheetProvider()
    provider.read_range(
        SheetRef(provider="wps", source_url="https://kdocs.cn/l/book-1", workbook_id="book-1", sheet_id="sheet-1"),
        "A1:Z10&foo=bar",
    )

    assert seen["url"].endswith("?range=A1%3AZ10%26foo%3Dbar")


def test_wps_native_cells_api_reads_sparse_cells(monkeypatch: pytest.MonkeyPatch):
    seen: dict[str, object] = {}
    monkeypatch.delenv("WPS_READ_URL_TEMPLATE", raising=False)
    monkeypatch.setenv("WPS_ACCESS_TOKEN", "token")
    monkeypatch.setenv("WPS_API_BASE_URL", "https://openapi.wps.cn")
    monkeypatch.setenv("WPS_SPREADSHEET_API_KIND", "et")

    def fake_get_json(url: str, headers: dict[str, str] | None = None, params: dict[str, str] | None = None):
        seen["url"] = url
        seen["params"] = params
        return {
            "code": 0,
            "data": {
                "cells": [
                    {"row": 0, "col": 0, "text": "序号"},
                    {"row": 0, "col": 1, "text": "问题描述"},
                    {"row": 1, "col": 0, "text": "1"},
                    {"row": 1, "col": 1, "text": "按钮无反馈"},
                ]
            },
        }

    monkeypatch.setattr("bugfix_automation.integrations.online_sheets.wps.get_json", fake_get_json)

    provider = WpsSheetProvider()
    table = provider.read_range(
        SheetRef(provider="wps", source_url="https://kdocs.cn/l/file-1", workbook_id="file-1", sheet_id="0"),
        "A1:B2",
    )

    assert seen["url"] == "https://openapi.wps.cn/api/v1/openapi/et/file-1/sheets/0/cells"
    assert seen["params"] == {"access_token": "token", "row_from": "0", "row_to": "1", "col_from": "0", "col_to": "1"}
    assert table.headers == ["序号", "问题描述"]
    assert table.rows == [{"序号": "1", "问题描述": "按钮无反馈"}]


def test_wps_reads_credentials_from_config_yaml(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
online_sheets:
  wps:
    access_token: yaml-token
    read_url_template: https://example.test/{workbook_id}/{sheet_id}?range={range}
""",
        encoding="utf-8",
    )
    for name in ("WPS_ACCESS_TOKEN", "WPS_READ_URL_TEMPLATE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("BUGFIX_CONFIG_PATH", str(config_path))
    seen: dict[str, object] = {}

    def fake_get_json(url: str, headers: dict[str, str] | None = None):
        seen["url"] = url
        seen["headers"] = headers
        return {"values": [["序号"], ["1"]]}

    monkeypatch.setattr("bugfix_automation.integrations.online_sheets.wps.get_json", fake_get_json)

    provider = WpsSheetProvider()
    table = provider.read_range(
        SheetRef(provider="wps", source_url="https://kdocs.cn/l/file-1", workbook_id="file-1", sheet_id="0"),
        "A1:A2",
    )

    assert seen["url"] == "https://example.test/file-1/0?range=A1%3AA2"
    assert seen["headers"] == {"Authorization": "Bearer yaml-token"}
    assert table.rows == [{"序号": "1"}]
