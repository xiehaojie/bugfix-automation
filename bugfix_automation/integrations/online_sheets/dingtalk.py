from __future__ import annotations

from urllib.parse import quote

from bugfix_automation.integrations.online_sheets.base import OnlineSheetError, SheetRef, SheetTable
from bugfix_automation.integrations.online_sheets.common import env_required, first_match, table_from_values
from bugfix_automation.integrations.online_sheets.http import get_json


class DingTalkSheetProvider:
    key = "dingtalk"
    label = "钉钉文档"

    def parse_url(self, url: str) -> SheetRef:
        workbook_id = first_match(
            [
                r"workbookId=([A-Za-z0-9_-]+)",
                r"/workbooks/([A-Za-z0-9_-]+)",
                r"/doc/([A-Za-z0-9_-]+)",
            ],
            url,
        )
        sheet_id = ""
        try:
            sheet_id = first_match([r"sheetId=([A-Za-z0-9_-]+)", r"/sheets/([A-Za-z0-9_-]+)"], url)
        except OnlineSheetError:
            sheet_id = env_required("DINGTALK_DEFAULT_SHEET_ID", "钉钉")
        return SheetRef(provider=self.key, source_url=url, workbook_id=workbook_id, sheet_id=sheet_id)

    def read_range(self, ref: SheetRef, range_address: str) -> SheetTable:
        access_token = env_required("DINGTALK_ACCESS_TOKEN", "钉钉")
        operator_id = env_required("DINGTALK_OPERATOR_ID", "钉钉")
        address = range_address.strip() or "A1:Z1000"
        data = get_json(
            "https://api.dingtalk.com/v1.0/doc/workbooks/"
            f"{quote(ref.workbook_id, safe='')}/sheets/{quote(ref.sheet_id, safe='')}/ranges/{quote(address, safe='')}",
            headers={"x-acs-dingtalk-access-token": access_token},
            params={"operatorId": operator_id},
        )
        values = data.get("values") or data.get("data", {}).get("values") or data.get("result", {}).get("values")
        return table_from_values(ref, address, values)

