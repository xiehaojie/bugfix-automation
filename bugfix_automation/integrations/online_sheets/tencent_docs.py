from __future__ import annotations

import json
import re
from urllib.parse import quote

from bugfix_automation.integrations.online_sheets.base import OnlineSheetError, SheetRef, SheetTable
from bugfix_automation.integrations.online_sheets.common import config_or_env, first_match, required_config_or_env, table_from_values
from bugfix_automation.integrations.online_sheets.http import get_json, post_json


class TencentDocsSheetProvider:
    key = "tencent_docs"
    label = "腾讯文档"

    def parse_url(self, url: str) -> SheetRef:
        workbook_id = first_match([r"/sheet/([A-Za-z0-9_-]+)", r"/doc/([A-Za-z0-9_-]+)", r"padId=([A-Za-z0-9_-]+)"], url)
        sheet_id = ""
        if "sheetId=" in url:
            sheet_id = first_match([r"sheetId=([A-Za-z0-9_-]+)"], url)
        return SheetRef(provider=self.key, source_url=url, workbook_id=workbook_id, sheet_id=sheet_id)

    def read_range(self, ref: SheetRef, range_address: str) -> SheetTable:
        template = config_or_env("TENCENT_DOCS_READ_URL_TEMPLATE", self.key, "read_url_template")
        address = range_address.strip() or "A1:Z1000"
        if not template:
            return self._read_from_mcp(ref, address)
        encoded_range = quote(address, safe="")
        url = template.format(
            workbook_id=quote(ref.workbook_id, safe=""),
            workbook_id_raw=ref.workbook_id,
            sheet_id=quote(ref.sheet_id, safe=""),
            sheet_id_raw=ref.sheet_id,
            range=encoded_range,
            range_encoded=encoded_range,
            range_raw=address,
        )
        data = get_json(
            url,
            headers={
                "Access-Token": required_config_or_env("TENCENT_DOCS_ACCESS_TOKEN", self.key, "access_token", "腾讯文档"),
                "Client-Id": required_config_or_env("TENCENT_DOCS_CLIENT_ID", self.key, "client_id", "腾讯文档"),
                "Open-Id": required_config_or_env("TENCENT_DOCS_OPEN_ID", self.key, "open_id", "腾讯文档"),
            },
        )
        values = data.get("values") or data.get("data", {}).get("values") or data.get("data", {}).get("rows")
        return table_from_values(ref, address, values)

    def _read_from_mcp(self, ref: SheetRef, address: str) -> SheetTable:
        mcp_url = config_or_env("TENCENT_DOCS_MCP_URL", self.key, "mcp_url", "https://docs.qq.com/openapi/mcp")
        token = required_config_or_env("TENCENT_DOCS_TOKEN", self.key, "token", "腾讯文档 MCP")
        tool_name = config_or_env("TENCENT_DOCS_MCP_TOOL", self.key, "mcp_tool", "get_content")
        arguments = _mcp_arguments(ref, address)
        data = post_json(
            mcp_url,
            {
                "jsonrpc": "2.0",
                "id": "bugfix-automation-online-sheet",
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments},
            },
            headers={
                "Authorization": token,
                "Accept": "application/json, text/event-stream",
            },
        )
        if data.get("error"):
            raise OnlineSheetError(f"腾讯文档 MCP 读取失败: {data['error']}")
        values = _values_from_mcp_response(data)
        return table_from_values(ref, address, values)


def _mcp_arguments(ref: SheetRef, address: str) -> dict[str, str]:
    template = config_or_env("TENCENT_DOCS_MCP_ARGUMENTS_TEMPLATE", "tencent_docs", "mcp_arguments_template")
    values = {
        "source_url": ref.source_url,
        "url": ref.source_url,
        "workbook_id": ref.workbook_id,
        "sheet_id": ref.sheet_id,
        "range": address,
    }
    if template:
        try:
            parsed = json.loads(template)
        except (KeyError, json.JSONDecodeError) as exc:
            raise OnlineSheetError(f"腾讯文档 MCP 参数模板不正确: {exc}") from exc
        if not isinstance(parsed, dict):
            raise OnlineSheetError("腾讯文档 MCP 参数模板必须渲染为 JSON object")
        return {str(key): str(value).format(**values) for key, value in parsed.items()}
    return {"url": ref.source_url}


def _values_from_mcp_response(data: dict) -> list[list[str]]:
    for candidate in (
        data.get("values"),
        data.get("result", {}).get("values"),
        data.get("result", {}).get("structuredContent", {}).get("values"),
        data.get("result", {}).get("structured_content", {}).get("values"),
    ):
        if isinstance(candidate, list):
            return candidate

    texts: list[str] = []
    content = data.get("result", {}).get("content") or data.get("content")
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                texts.append(item["text"])
            elif isinstance(item, str):
                texts.append(item)
    elif isinstance(content, str):
        texts.append(content)
    text = "\n".join(texts).strip()
    if not text:
        return []
    return _values_from_text(text)


def _values_from_text(text: str) -> list[list[str]]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict):
        values = parsed.get("values") or parsed.get("data", {}).get("values")
        if isinstance(values, list):
            return values
    if isinstance(parsed, list):
        return parsed

    markdown_rows = _markdown_table_values(text)
    if markdown_rows:
        return markdown_rows
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return []
    separator = "\t" if any("\t" in line for line in lines) else ","
    return [[cell.strip() for cell in line.split(separator)] for line in lines]


def _markdown_table_values(text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if cells and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        rows.append(cells)
    return rows
