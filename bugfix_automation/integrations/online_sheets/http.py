from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from bugfix_automation.integrations.online_sheets.base import OnlineSheetError


def get_json(url: str, headers: dict[str, str] | None = None, params: dict[str, str] | None = None) -> dict[str, Any]:
    target = url
    if params:
        separator = "&" if "?" in target else "?"
        target = f"{target}{separator}{urlencode(params)}"
    return request_json("GET", target, headers=headers)


def post_json(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
    return request_json("POST", url, headers=headers, payload=payload)


def request_json(
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body = None
    request_headers = {"Accept": "application/json", **(headers or {})}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = Request(url, data=body, headers=request_headers, method=method)
    try:
        with urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise OnlineSheetError(f"在线表格接口请求失败 ({exc.code}): {detail[:500]}") from exc
    except Exception as exc:
        raise OnlineSheetError(f"在线表格接口请求失败: {exc}") from exc

    try:
        data = json.loads(_json_payload_from_raw(raw)) if raw else {}
    except json.JSONDecodeError as exc:
        raise OnlineSheetError("在线表格接口没有返回 JSON") from exc
    if not isinstance(data, dict):
        raise OnlineSheetError("在线表格接口返回格式不正确")
    return data


def _json_payload_from_raw(raw: str) -> str:
    text = raw.strip()
    if text.startswith("data:"):
        for line in text.splitlines():
            if line.startswith("data:"):
                candidate = line.removeprefix("data:").strip()
                if candidate and candidate != "[DONE]":
                    return candidate
    return text
