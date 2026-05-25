from __future__ import annotations

import os
from urllib.parse import quote

from bugfix_automation.integrations.online_sheets.base import OnlineSheetError, SheetRef, SheetTable
from bugfix_automation.integrations.online_sheets.common import env_required, first_match, table_from_values
from bugfix_automation.integrations.online_sheets.http import get_json, post_json


class FeishuSheetProvider:
    key = "feishu"
    label = "飞书文档"

    def parse_url(self, url: str) -> SheetRef:
        workbook_id = first_match(
            [
                r"/sheets/([A-Za-z0-9]+)",
                r"spreadsheetToken=([A-Za-z0-9]+)",
                r"token=([A-Za-z0-9]+)",
            ],
            url,
        )
        sheet_id = ""
        if "sheet=" in url:
            sheet_id = first_match([r"sheet=([A-Za-z0-9_-]+)"], url)
        return SheetRef(provider=self.key, source_url=url, workbook_id=workbook_id, sheet_id=sheet_id)

    def read_range(self, ref: SheetRef, range_address: str) -> SheetTable:
        token = _tenant_access_token()
        address = range_address.strip() or "A1:Z1000"
        if "!" not in address and ref.sheet_id:
            address = f"{ref.sheet_id}!{address}"
        data = get_json(
            f"https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{ref.workbook_id}/values/{quote(address, safe='')}",
            headers={"Authorization": f"Bearer {token}"},
        )
        if data.get("code") not in (0, None):
            raise OnlineSheetError(f"飞书读取失败: {data.get('msg') or data.get('message') or data}")
        values = (
            data.get("data", {})
            .get("valueRange", {})
            .get("values", [])
        )
        return table_from_values(ref, address, values)


def _tenant_access_token() -> str:
    env_token = os.environ.get("FEISHU_TENANT_ACCESS_TOKEN", "").strip()
    if env_token:
        return env_token
    app_id = env_required("FEISHU_APP_ID", "飞书")
    app_secret = env_required("FEISHU_APP_SECRET", "飞书")
    data = post_json(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        {"app_id": app_id, "app_secret": app_secret},
    )
    token = str(data.get("tenant_access_token") or "").strip()
    if not token:
        raise OnlineSheetError(f"飞书 tenant_access_token 获取失败: {data.get('msg') or data}")
    return token

