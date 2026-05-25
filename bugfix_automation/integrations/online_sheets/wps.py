from __future__ import annotations

from urllib.parse import quote

from bugfix_automation.integrations.online_sheets.base import OnlineSheetError, SheetRef, SheetTable
from bugfix_automation.integrations.online_sheets.common import config_or_env, first_match, range_to_zero_based_bounds, required_config_or_env, table_from_values
from bugfix_automation.integrations.online_sheets.http import get_json


class WpsSheetProvider:
    key = "wps"
    label = "金山文档/WPS"

    def parse_url(self, url: str) -> SheetRef:
        workbook_id = first_match(
            [
                r"/s/([A-Za-z0-9_-]+)",
                r"/l/([A-Za-z0-9_-]+)",
                r"file_id=([A-Za-z0-9_-]+)",
                r"file_token=([A-Za-z0-9_-]+)",
            ],
            url,
        )
        sheet_id = ""
        if "sheetId=" in url:
            sheet_id = first_match([r"sheetId=([A-Za-z0-9_-]+)"], url)
        elif "sheet_idx=" in url:
            sheet_id = first_match([r"sheet_idx=([0-9]+)"], url)
        else:
            sheet_id = config_or_env("WPS_DEFAULT_SHEET_IDX", self.key, "default_sheet_idx", "0")
        return SheetRef(provider=self.key, source_url=url, workbook_id=workbook_id, sheet_id=sheet_id)

    def read_range(self, ref: SheetRef, range_address: str) -> SheetTable:
        template = config_or_env("WPS_READ_URL_TEMPLATE", self.key, "read_url_template")
        address = range_address.strip() or "A1:Z1000"
        if not template:
            return self._read_native_cells(ref, address)
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
        data = get_json(url, headers={"Authorization": f"Bearer {required_config_or_env('WPS_ACCESS_TOKEN', self.key, 'access_token', 'WPS/金山文档')}"})
        values = data.get("values") or data.get("data", {}).get("values") or data.get("data", {}).get("rows")
        return table_from_values(ref, address, values)

    def _read_native_cells(self, ref: SheetRef, address: str) -> SheetTable:
        access_token = required_config_or_env("WPS_ACCESS_TOKEN", self.key, "access_token", "WPS/金山文档")
        bounds = range_to_zero_based_bounds(address)
        base_url = config_or_env("WPS_API_BASE_URL", self.key, "api_base_url", "https://openapi.wps.cn").rstrip("/")
        api_kind = config_or_env("WPS_SPREADSHEET_API_KIND", self.key, "spreadsheet_api_kind", "et")
        sheet_idx = ref.sheet_id or config_or_env("WPS_DEFAULT_SHEET_IDX", self.key, "default_sheet_idx", "0")
        data = get_json(
            f"{base_url}/api/v1/openapi/{quote(api_kind, safe='')}/"
            f"{quote(ref.workbook_id, safe='')}/sheets/{quote(sheet_idx, safe='')}/cells",
            params={
                "access_token": access_token,
                "row_from": str(bounds["row_from"]),
                "row_to": str(bounds["row_to"]),
                "col_from": str(bounds["col_from"]),
                "col_to": str(bounds["col_to"]),
            },
        )
        code = data.get("code")
        if code not in (0, "0", None):
            raise OnlineSheetError(f"WPS/金山文档读取失败: {data.get('msg') or data.get('message') or data}")
        values = _wps_values_from_response(data, bounds)
        return table_from_values(ref, address, values)


def _wps_values_from_response(data: dict, bounds: dict[str, int]) -> list[list[str]]:
    nested_values = data.get("values") or data.get("data", {}).get("values") or data.get("data", {}).get("rows")
    if isinstance(nested_values, list) and nested_values and isinstance(nested_values[0], list):
        return nested_values

    cells = data.get("cells") or data.get("data", {}).get("cells") or data.get("result", {}).get("cells") or nested_values
    row_count = bounds["row_to"] - bounds["row_from"] + 1
    col_count = bounds["col_to"] - bounds["col_from"] + 1
    matrix = [["" for _ in range(col_count)] for _ in range(row_count)]
    if not isinstance(cells, list):
        return matrix
    for cell in cells:
        if not isinstance(cell, dict):
            continue
        row_index = _first_int(cell, ["row", "row_idx", "rowIndex", "row_index"])
        col_index = _first_int(cell, ["col", "col_idx", "colIndex", "col_index"])
        if row_index is None or col_index is None:
            continue
        if row_index >= bounds["row_from"] and col_index >= bounds["col_from"]:
            row_offset = row_index - bounds["row_from"]
            col_offset = col_index - bounds["col_from"]
        else:
            row_offset = row_index
            col_offset = col_index
        if 0 <= row_offset < row_count and 0 <= col_offset < col_count:
            matrix[row_offset][col_offset] = _cell_value(cell)
    return matrix


def _first_int(payload: dict, keys: list[str]) -> int | None:
    for key in keys:
        if key in payload:
            try:
                return int(payload[key])
            except (TypeError, ValueError):
                return None
    return None


def _cell_value(cell: dict) -> str:
    for key in ("text", "value", "formatted_value"):
        if key in cell and cell[key] is not None:
            return str(cell[key])
    return ""
