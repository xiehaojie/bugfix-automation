from __future__ import annotations

import asyncio
from datetime import datetime
import json
import shlex
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import uuid4

from bugfix_automation.config import CanonicalFieldMapping, Config, ExcelProfile, FilterRule, repo_root_path
from bugfix_automation.excel_reader import read_sheet
from bugfix_automation.storage.settings import set_setting

ALLOWED_FILTER_OPS = {"equals", "not_equals", "in", "any_in", "all_in", "not_in", "non_empty", "empty"}
PROMPT_TEMPLATE_PATH = repo_root_path() / "prompts" / "excel_adapter.md"
_ANALYSIS_LOCK = asyncio.Lock()
_ACTIVE_ANALYSIS: dict[str, str] = {}


def sanitize_adapter_suggestion(
    suggestion: dict[str, Any] | None,
    headers: list[str] | tuple[str, ...],
    require_description: bool = False,
) -> dict[str, Any]:
    header_list = [str(header).strip() for header in headers if str(header).strip()]
    header_set = set(header_list)
    valid_canonical_fields = set(CanonicalFieldMapping.__dataclass_fields__)

    cleaned: dict[str, Any] = {
        "canonical_fields": {},
        "prompt": {"fields": [], "template": "", "context_paths": []},
        "branch_summary_fields": [],
        "filters": [],
        "warnings": [],
    }

    if not isinstance(suggestion, dict):
        if require_description:
            raise ValueError("请先选择 description 对应的 Excel 列")
        return cleaned

    warnings: list[str] = cleaned["warnings"]

    raw_canonical_fields = suggestion.get("canonical_fields")
    if isinstance(raw_canonical_fields, dict):
        for key, value in raw_canonical_fields.items():
            field_name = str(key).strip()
            header_name = str(value).strip()
            if field_name not in valid_canonical_fields:
                warnings.append(f"已忽略未知 canonical_fields 字段: {field_name}")
                continue
            if not header_name:
                continue
            if header_name not in header_set:
                warnings.append(f"已忽略 {field_name} 映射到不存在的列: {header_name}")
                continue
            cleaned["canonical_fields"][field_name] = header_name

    if require_description and "description" not in cleaned["canonical_fields"]:
        raise ValueError("请先选择 description 对应的 Excel 列")

    raw_prompt = suggestion.get("prompt")
    if isinstance(raw_prompt, dict):
        cleaned["prompt"]["fields"] = _clean_header_list(raw_prompt.get("fields"), header_set)
        template = raw_prompt.get("template")
        if template is not None:
            cleaned["prompt"]["template"] = str(template)
        cleaned["prompt"]["context_paths"] = _clean_text_list(raw_prompt.get("context_paths"))

    cleaned["branch_summary_fields"] = _clean_header_list(suggestion.get("branch_summary_fields"), header_set)
    cleaned["filters"] = _clean_filters(suggestion.get("filters"), header_set, warnings)
    return cleaned


async def analyze_excel_adapter(config: Config, cli_tool: str = "") -> dict[str, Any]:
    if _ANALYSIS_LOCK.locked():
        log_path = _ACTIVE_ANALYSIS.get("log_path", "")
        return {
            "ok": False,
            "error": "已有 AI 识别任务正在运行，请等待当前识别完成后再试。",
            "log_path": log_path,
        }

    async with _ANALYSIS_LOCK:
        try:
            return await _analyze_excel_adapter_locked(config, cli_tool)
        finally:
            _ACTIVE_ANALYSIS.clear()


async def _analyze_excel_adapter_locked(config: Config, cli_tool: str = "") -> dict[str, Any]:
    log_dir = _analysis_log_dir(config)
    log_path = log_dir / "analyze.log"
    result_path = log_dir / "adapter.json"
    _ACTIVE_ANALYSIS.clear()
    _ACTIVE_ANALYSIS.update({"log_path": str(log_path), "result_path": str(result_path)})
    selected_cli_tool = cli_tool.strip() or config.cli_tool
    payload: dict[str, Any] = {}
    prompt_text = ""
    raw_stdout = ""
    raw_stderr = ""
    suggestion: dict[str, Any] | None = None
    cleaned: dict[str, Any] | None = None
    error = ""

    try:
        rows = read_sheet(config.excel_path, config.sheet_name)
        headers = _extract_headers(rows)
    except Exception as exc:
        error = str(exc)
        _write_analysis_log(log_path, payload, prompt_text, raw_stdout, raw_stderr, suggestion, cleaned, error)
        return {"ok": False, "error": error, "log_path": str(log_path), "result_path": str(result_path)}

    payload = {
        "excel_path": str(config.excel_path),
        "sheet_name": config.sheet_name,
        "cli_tool": selected_cli_tool,
        "headers": headers,
        "sample_rows": rows[:3],
        "active_workspace": config.active_workspace,
        "filters": [
            {"field": rule.field, "op": rule.op, "value": rule.value, "values": list(rule.values)}
            for rule in config.filters
        ],
        "prompt": {
            "fields": list(config.prompt_fields),
            "template": config.prompt_template,
            "context_paths": list(config.prompt_context_paths),
        },
        "excel_profile": {
            "canonical_fields": {
                field_name: getattr(config.excel_profile.canonical_fields, field_name)
                for field_name in CanonicalFieldMapping.__dataclass_fields__
            },
            "prompt": {
                "fields": list(config.excel_profile.prompt_fields),
                "template": config.excel_profile.prompt_template,
                "context_paths": list(config.excel_profile.prompt_context_paths),
                "branch_summary_fields": list(config.excel_profile.branch_summary_fields),
            },
        },
    }

    try:
        prompt_text = _load_prompt_template().format(payload_json=json.dumps(payload, ensure_ascii=False, indent=2))
    except Exception as exc:
        error = str(exc)
        _write_analysis_log(log_path, payload, prompt_text, raw_stdout, raw_stderr, suggestion, cleaned, error)
        return {"ok": False, "error": error, "log_path": str(log_path), "result_path": str(result_path)}

    try:
        suggestion, raw_stdout, raw_stderr = await _run_cli_json(selected_cli_tool, prompt_text)
    except Exception as exc:
        error = str(exc)
        _write_analysis_log(log_path, payload, prompt_text, raw_stdout, raw_stderr, suggestion, cleaned, error)
        return {"ok": False, "error": error, "log_path": str(log_path), "result_path": str(result_path)}

    cleaned = sanitize_adapter_suggestion(suggestion, headers)
    result_path.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_analysis_log(log_path, payload, prompt_text, raw_stdout, raw_stderr, suggestion, cleaned, error)
    return {"ok": True, "adapter": cleaned, "log_path": str(log_path), "result_path": str(result_path), "cli_tool": selected_cli_tool}


def save_excel_adapter(config: Config, adapter: dict[str, Any] | None) -> dict[str, Any]:
    try:
        rows = read_sheet(config.excel_path, config.sheet_name)
        headers = _extract_headers(rows)
        cleaned = sanitize_adapter_suggestion(adapter, headers, require_description=True)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    canonical_fields = cleaned["canonical_fields"]
    prompt_fields = cleaned["prompt"]["fields"]
    prompt_template = cleaned["prompt"]["template"]
    branch_summary_fields = cleaned["branch_summary_fields"]
    filter_rules = cleaned["filters"]

    excel_profile = ExcelProfile(
        canonical_fields=_canonical_mapping_from_dict(canonical_fields),
        prompt_fields=tuple(prompt_fields),
        prompt_template=str(prompt_template),
        prompt_context_paths=(),
        branch_summary_fields=tuple(branch_summary_fields),
        prompt_fields_provided=True,
        prompt_template_provided=True,
        prompt_context_paths_provided=False,
        branch_summary_fields_provided=True,
    )

    set_setting(
        config.storage_db_path,
        "excel_profile",
        {
            "canonical_fields": canonical_fields,
            "prompt": {
                "fields": prompt_fields,
                "template": prompt_template,
                "branch_summary_fields": branch_summary_fields,
            },
        },
    )
    set_setting(
        config.storage_db_path,
        "prompt",
        {
            "fields": prompt_fields,
            "template": prompt_template,
            "context_paths": list(config.prompt_context_paths),
        },
    )
    set_setting(config.storage_db_path, "branch_summary_fields", branch_summary_fields)
    if filter_rules:
        set_setting(config.storage_db_path, "filters", filter_rules)

    saved_filters = tuple(
        FilterRule(
            field=rule.field,
            op=rule.op,
            value=rule.value,
            values=tuple(rule.values),
        )
        for rule in config.filters
    )
    if filter_rules:
        saved_filters = tuple(
            FilterRule(
                field=str(rule.get("field", "")).strip(),
                op=str(rule.get("op", "equals")).strip() or "equals",
                value=str(rule.get("value", "")).strip(),
                values=_clean_text_tuple(rule.get("values")),
            )
            for rule in filter_rules
        )

    from bugfix_automation.application.config_service import config_payload

    updated_config = replace(
        config,
        filters=saved_filters,
        branch_summary_fields=tuple(branch_summary_fields),
        prompt_fields=tuple(prompt_fields),
        prompt_template=str(prompt_template),
        prompt_context_paths=tuple(config.prompt_context_paths),
        excel_profile=excel_profile,
    )
    return {"ok": True, "config": config_payload(updated_config)}


def _load_prompt_template() -> str:
    if not PROMPT_TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Prompt template not found: {PROMPT_TEMPLATE_PATH}")
    return PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8").strip()


async def _run_cli_json(cli_tool: str, prompt_text: str) -> tuple[dict[str, Any], str, str]:
    tool = cli_tool.strip()
    if not tool:
        raise ValueError("cli_tool 不能为空")
    args = [*shlex.split(tool), "exec", "-"]
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"未找到命令: {cli_tool}") from exc

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(prompt_text.encode("utf-8")), timeout=120)
    except asyncio.TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise TimeoutError("Excel 适配分析超时（120s）") from exc

    if proc.returncode != 0:
        err = stderr.decode(errors="replace").strip()
        raise RuntimeError(err or f"CLI 退出码 {proc.returncode}")

    raw_stdout = stdout.decode(errors="replace").strip()
    raw_stderr = stderr.decode(errors="replace").strip()
    if not raw_stdout:
        raise ValueError("CLI 没有返回 JSON")
    try:
        parsed = json.loads(raw_stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"CLI 返回的不是有效 JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("CLI 返回的 JSON 不是对象")
    return parsed, raw_stdout, raw_stderr


def _analysis_log_dir(config: Config) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_id = uuid4().hex[:8]
    path = config.logs_root / "excel-adapter" / f"{stamp}-{run_id}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_analysis_log(
    log_path: Path,
    payload: dict[str, Any],
    prompt_text: str,
    raw_stdout: str,
    raw_stderr: str,
    suggestion: dict[str, Any] | None,
    cleaned: dict[str, Any] | None,
    error: str,
) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    sections = [
        "# Excel Adapter Analyze",
        f"created_at: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## payload.json",
        json.dumps(payload, ensure_ascii=False, indent=2),
        "",
        "## prompt",
        prompt_text,
        "",
        "## raw_stdout",
        raw_stdout,
        "",
        "## raw_stderr",
        raw_stderr,
        "",
        "## parsed_suggestion.json",
        json.dumps(suggestion or {}, ensure_ascii=False, indent=2),
        "",
        "## cleaned_adapter.json",
        json.dumps(cleaned or {}, ensure_ascii=False, indent=2),
    ]
    if error:
        sections.extend(["", "## error", error])
    log_path.write_text("\n".join(sections).rstrip() + "\n", encoding="utf-8")


def _extract_headers(rows: list[dict[str, str]]) -> list[str]:
    headers: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row.keys():
            if key == "_excel_row" or key in seen:
                continue
            seen.add(key)
            headers.append(key)
    return headers


def _clean_header_list(value: Any, header_set: set[str]) -> list[str]:
    items = _clean_text_list(value)
    return [item for item in items if item in header_set]


def _clean_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, (list, tuple)):
        seen: set[str] = set()
        result: list[str] = []
        for item in value:
            text = str(item).strip()
            if text and text not in seen:
                seen.add(text)
                result.append(text)
        return result
    text = str(value).strip()
    return [text] if text else []


def _clean_text_tuple(value: Any) -> tuple[str, ...]:
    return tuple(_clean_text_list(value))


def _clean_filters(value: Any, header_set: set[str], warnings: list[str]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    cleaned: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        field = str(item.get("field", "")).strip()
        op = str(item.get("op", "equals")).strip() or "equals"
        if not field or field not in header_set:
            warnings.append(f"已忽略不存在的筛选字段: {field or '<空>'}")
            continue
        if op not in ALLOWED_FILTER_OPS:
            warnings.append(f"已忽略 {field} 的无效筛选操作: {op}")
            continue
        rule: dict[str, Any] = {"field": field, "op": op}
        if "value" in item and item.get("value") is not None:
            value_text = str(item.get("value", "")).strip()
            if value_text:
                rule["value"] = value_text
        if "values" in item and item.get("values") is not None:
            values = _clean_text_list(item.get("values"))
            if values:
                rule["values"] = values
        if op in {"equals", "not_equals"} and "value" not in rule and "values" in rule and rule["values"]:
            rule["value"] = rule["values"][0]
        if op not in {"non_empty", "empty"} and "value" not in rule and "values" not in rule:
            warnings.append(f"已忽略 {field} 的空筛选条件")
            continue
        cleaned.append(rule)
    return cleaned


def _canonical_mapping_from_dict(values: dict[str, str]) -> CanonicalFieldMapping:
    default_mapping = CanonicalFieldMapping()
    mapping_kwargs: dict[str, str] = {}
    for field_name in CanonicalFieldMapping.__dataclass_fields__:
        mapping_kwargs[field_name] = values.get(field_name, getattr(default_mapping, field_name))
    return CanonicalFieldMapping(**mapping_kwargs)
