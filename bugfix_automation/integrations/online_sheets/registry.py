from __future__ import annotations

from bugfix_automation.integrations.online_sheets.base import OnlineSheetProvider
from bugfix_automation.integrations.online_sheets.dingtalk import DingTalkSheetProvider
from bugfix_automation.integrations.online_sheets.feishu import FeishuSheetProvider
from bugfix_automation.integrations.online_sheets.tencent_docs import TencentDocsSheetProvider
from bugfix_automation.integrations.online_sheets.wps import WpsSheetProvider


_PROVIDERS: dict[str, OnlineSheetProvider] = {
    "feishu": FeishuSheetProvider(),
    "dingtalk": DingTalkSheetProvider(),
    "tencent_docs": TencentDocsSheetProvider(),
    "wps": WpsSheetProvider(),
}


def provider_keys() -> list[str]:
    return sorted(_PROVIDERS)


def provider_options() -> list[dict[str, str]]:
    return [{"key": key, "label": provider.label} for key, provider in sorted(_PROVIDERS.items())]


def get_provider(key: str) -> OnlineSheetProvider:
    provider_key = key.strip()
    if provider_key not in _PROVIDERS:
        raise ValueError(f"不支持的在线表格平台：{key}")
    return _PROVIDERS[provider_key]

