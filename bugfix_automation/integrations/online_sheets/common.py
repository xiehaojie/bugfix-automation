from __future__ import annotations

import os
import re
from typing import Any

from bugfix_automation.config import read_config_section
from bugfix_automation.integrations.online_sheets.base import OnlineSheetAuthError, OnlineSheetError, SheetRef, SheetTable

MAX_RANGE_ROWS = 2000
MAX_RANGE_COLS = 100
MAX_RANGE_CELLS = 100_000


def env_required(name: str, provider_label: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise OnlineSheetAuthError(f"{provider_label} 未配置 {name}")
    return value


def first_match(patterns: list[str], text: str) -> str:
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    raise OnlineSheetError("无法从链接中识别文档 ID，请检查链接或手动配置文档 ID")


def provider_config(provider_key: str) -> dict[str, Any]:
    online_sheets = read_config_section("online_sheets")
    value = online_sheets.get(provider_key)
    return value if isinstance(value, dict) else {}


def config_or_env(env_name: str, provider_key: str, key: str, default: str = "") -> str:
    env_value = os.environ.get(env_name, "").strip()
    if env_value:
        return env_value
    value = provider_config(provider_key).get(key, default)
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def required_config_or_env(env_name: str, provider_key: str, key: str, provider_label: str) -> str:
    value = config_or_env(env_name, provider_key, key)
    if not value:
        raise OnlineSheetAuthError(f"{provider_label} 未配置 {env_name} 或 config.yaml 中的 online_sheets.{provider_key}.{key}")
    return value


def table_from_values(ref: SheetRef, range_address: str, values: Any) -> SheetTable:
    if not isinstance(values, list) or not values:
        return SheetTable(ref=ref, range_address=range_address, headers=[], rows=[])
    matrix = [[_cell_text(cell) for cell in row] for row in values if isinstance(row, list)]
    if not matrix:
        return SheetTable(ref=ref, range_address=range_address, headers=[], rows=[])
    headers = _unique_headers(matrix[0])
    rows: list[dict[str, str]] = []
    for raw_row in matrix[1:]:
        row = {header: raw_row[index] if index < len(raw_row) else "" for index, header in enumerate(headers)}
        if any(value for value in row.values()):
            rows.append(row)
    return SheetTable(ref=ref, range_address=range_address, headers=headers, rows=rows)


def normalize_range_address(range_address: str) -> str:
    address = range_address.strip().upper()
    if not address:
        raise OnlineSheetError("读取范围不能为空")
    match = re.fullmatch(r"([A-Z]+)(\d+)(?::([A-Z]+)(\d+))?", address)
    if not match:
        raise OnlineSheetError("读取范围格式不正确，请使用类似 A1:Z1000 的写法")
    start_col, start_row, end_col, end_row = match.groups()
    start_col_index = _column_index(start_col)
    end_col_index = _column_index(end_col or start_col)
    start_row_num = int(start_row)
    end_row_num = int(end_row or start_row)
    if start_row_num < 1 or end_row_num < 1:
        raise OnlineSheetError("读取范围行号必须大于 0")
    if end_col_index < start_col_index or end_row_num < start_row_num:
        raise OnlineSheetError("读取范围开始位置不能大于结束位置")
    row_count = end_row_num - start_row_num + 1
    col_count = end_col_index - start_col_index + 1
    cell_count = row_count * col_count
    if row_count > MAX_RANGE_ROWS or col_count > MAX_RANGE_COLS or cell_count > MAX_RANGE_CELLS:
        raise OnlineSheetError(
            f"读取范围过大，最多支持 {MAX_RANGE_ROWS} 行、{MAX_RANGE_COLS} 列、{MAX_RANGE_CELLS} 个单元格"
        )
    start = f"{start_col}{start_row_num}"
    end = f"{end_col or start_col}{end_row_num}"
    return start if start == end else f"{start}:{end}"


def range_to_zero_based_bounds(range_address: str) -> dict[str, int]:
    address = normalize_range_address(range_address)
    match = re.fullmatch(r"([A-Z]+)(\d+)(?::([A-Z]+)(\d+))?", address)
    if not match:
        raise OnlineSheetError("读取范围格式不正确，请使用类似 A1:Z1000 的写法")
    start_col, start_row, end_col, end_row = match.groups()
    return {
        "row_from": int(start_row) - 1,
        "row_to": int(end_row or start_row) - 1,
        "col_from": _column_index(start_col) - 1,
        "col_to": _column_index(end_col or start_col) - 1,
    }


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    return str(value).strip()


def _unique_headers(raw_headers: list[str]) -> list[str]:
    headers: list[str] = []
    seen: dict[str, int] = {}
    for index, raw in enumerate(raw_headers, start=1):
        base = raw.strip() or f"列{index}"
        count = seen.get(base, 0)
        seen[base] = count + 1
        headers.append(base if count == 0 else f"{base}_{count + 1}")
    return headers


def _column_index(column: str) -> int:
    value = 0
    for char in column:
        value = value * 26 + (ord(char) - ord("A") + 1)
    return value
