# Excel AI Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move mutable automation configuration into SQLite and add an AI-assisted Excel adapter that generates field mappings and Excel-specific prompt settings.

**Architecture:** Keep `config.yaml` as bootstrap and compatibility fallback, then merge SQLite `app_settings` over YAML during `load_config`. Normalize raw Excel rows into `BugRecord` through a configurable `ExcelProfile`, and expose an adapter API/UI that lets AI propose mappings and prompt settings before users save them.

**Tech Stack:** Python 3 dataclasses, FastAPI, SQLite, unittest/pytest, Next.js/React/TypeScript.

---

## File Structure

- Modify `bugfix_automation/storage/schema.sql`: add `app_settings`.
- Create `bugfix_automation/storage/settings.py`: focused helpers for reading/writing JSON settings.
- Modify `bugfix_automation/config.py`: add profile dataclasses, SQLite merge, config export helpers.
- Modify `bugfix_automation/application/config_service.py`: save runtime config into SQLite instead of YAML.
- Modify `bugfix_automation/application/excel_service.py`: save selected/uploaded Excel path into SQLite.
- Modify `bugfix_automation/application/scheduler_service.py`: save schedule into SQLite.
- Modify `bugfix_automation/filtering.py`: create `bug_record_from_row` and use configurable canonical field mapping.
- Modify `bugfix_automation/prompt.py`: include raw Excel row fields in rendered prompts.
- Create `bugfix_automation/application/excel_adapter_service.py`: analyze/save Excel adapter suggestions.
- Modify `bugfix_automation/api/schemas.py`: add adapter request schemas.
- Modify `bugfix_automation/api/routes/excel.py`: add adapter routes.
- Create `prompts/excel_adapter.md`: strict JSON instruction for AI adapter.
- Modify `approval-web/src/features/approval/types.ts`: add `ExcelProfile` and adapter types.
- Modify `approval-web/src/features/approval/hooks/useApprovalDashboard.ts`: expose adapter actions/state.
- Create `approval-web/src/features/approval/components/ExcelAdapterPanel.tsx`: UI for analyzing and saving adapter settings.
- Modify `approval-web/app/page.tsx`: place adapter panel in configuration area.
- Add/modify tests in `tests/test_storage.py`, `tests/test_config.py`, `tests/test_filtering_prompt_report.py`, `tests/test_excel_adapter_service.py`, and API tests as needed.

---

### Task 1: SQLite App Settings Storage

**Files:**
- Modify: `bugfix_automation/storage/schema.sql`
- Create: `bugfix_automation/storage/settings.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write failing storage tests**

Add these tests to `tests/test_storage.py`:

```python
from bugfix_automation.storage.settings import get_setting, get_settings, set_setting


def test_app_settings_round_trip_json(tmp_path: Path) -> None:
    db_path = tmp_path / "app.sqlite3"

    set_setting(db_path, "prompt", {"fields": ["问题描述"], "template": "先修前端"})

    assert get_setting(db_path, "prompt") == {"fields": ["问题描述"], "template": "先修前端"}
    assert get_settings(db_path)["prompt"] == {"fields": ["问题描述"], "template": "先修前端"}


def test_get_setting_returns_default_for_missing_key(tmp_path: Path) -> None:
    db_path = tmp_path / "app.sqlite3"

    assert get_setting(db_path, "missing", {"ok": True}) == {"ok": True}
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python3 -m pytest tests/test_storage.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'bugfix_automation.storage.settings'`.

- [ ] **Step 3: Add `app_settings` schema**

Append to `bugfix_automation/storage/schema.sql` after `config_snapshots`:

```sql
CREATE TABLE IF NOT EXISTS app_settings (
  key TEXT PRIMARY KEY,
  value_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
```

- [ ] **Step 4: Implement settings helpers**

Create `bugfix_automation/storage/settings.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bugfix_automation.storage.db import connect, ensure_schema
from bugfix_automation.storage.repositories import utc_now


def get_settings(db_path: Path) -> dict[str, Any]:
    ensure_schema(db_path)
    with connect(db_path) as db:
        rows = db.execute("SELECT key, value_json FROM app_settings").fetchall()
    settings: dict[str, Any] = {}
    for row in rows:
        try:
            settings[str(row["key"])] = json.loads(str(row["value_json"]))
        except json.JSONDecodeError:
            settings[str(row["key"])] = None
    return settings


def get_setting(db_path: Path, key: str, default: Any = None) -> Any:
    ensure_schema(db_path)
    with connect(db_path) as db:
        row = db.execute("SELECT value_json FROM app_settings WHERE key = ?", (key,)).fetchone()
    if row is None:
        return default
    try:
        return json.loads(str(row["value_json"]))
    except json.JSONDecodeError:
        return default


def set_setting(db_path: Path, key: str, value: Any) -> None:
    ensure_schema(db_path)
    with connect(db_path) as db:
        db.execute(
            "INSERT INTO app_settings(key, value_json, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json, updated_at = excluded.updated_at",
            (key, json.dumps(value, ensure_ascii=False, sort_keys=True), utc_now()),
        )
        db.commit()
```

- [ ] **Step 5: Run storage tests**

Run: `python3 -m pytest tests/test_storage.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add bugfix_automation/storage/schema.sql bugfix_automation/storage/settings.py tests/test_storage.py
git commit -m "feat: add sqlite runtime settings"
```

---

### Task 2: Config Model and SQLite Merge

**Files:**
- Modify: `bugfix_automation/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing config merge tests**

Add to `tests/test_config.py`:

```python
from bugfix_automation.storage.settings import set_setting


def test_load_config_merges_sqlite_settings_over_yaml(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config.yaml"
        db_path = root / "data" / "app.sqlite3"
        config_path.write_text(
            f"""
storage_db_path: {db_path}
excel_path: /tmp/from-yaml.xlsx
sheet_name: SheetFromYaml
max_concurrency: 1
prompt:
  fields: 问题描述
  template: yaml template
""",
            encoding="utf-8",
        )
        set_setting(db_path, "excel", {"excel_path": "/tmp/from-sqlite.xlsx", "sheet_name": "SheetFromDb"})
        set_setting(db_path, "automation", {"max_concurrency": 4})
        set_setting(db_path, "prompt", {"fields": ["标题", "详情"], "template": "db template", "context_paths": []})

        config = load_config(config_path)

    self.assertEqual(config.excel_path, Path("/tmp/from-sqlite.xlsx"))
    self.assertEqual(config.sheet_name, "SheetFromDb")
    self.assertEqual(config.max_concurrency, 4)
    self.assertEqual(config.prompt_fields, ("标题", "详情"))
    self.assertEqual(config.prompt_template, "db template")


def test_load_config_reads_excel_profile_from_sqlite(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        config_path = root / "config.yaml"
        db_path = root / "data" / "app.sqlite3"
        config_path.write_text(f"storage_db_path: {db_path}\n", encoding="utf-8")
        set_setting(
            db_path,
            "excel_profile",
            {
                "canonical_fields": {"issue_id": "编号", "description": "标题", "assignee": "负责人"},
                "prompt": {
                    "fields": ["标题", "详情"],
                    "template": "adapter template",
                    "branch_summary_fields": ["标题"],
                },
            },
        )

        config = load_config(config_path)

    self.assertEqual(config.excel_profile.canonical_fields.issue_id, "编号")
    self.assertEqual(config.excel_profile.canonical_fields.description, "标题")
    self.assertEqual(config.prompt_fields, ("标题", "详情"))
    self.assertEqual(config.prompt_template, "adapter template")
    self.assertEqual(config.branch_summary_fields, ("标题",))
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python3 -m pytest tests/test_config.py -q`

Expected: FAIL because `Config` has no `excel_profile` and `load_config` ignores SQLite settings.

- [ ] **Step 3: Add dataclasses and default mapping**

In `bugfix_automation/config.py`, add:

```python
@dataclass(frozen=True)
class CanonicalFieldMapping:
    issue_id: str = "序号"
    source_system: str = "来源系统"
    priority: str = "优先级"
    primary_category: str = "一级分类"
    secondary_category: str = "二级分类"
    requester: str = "提出人"
    request_date: str = "提出日期"
    requester_status: str = "提出人状态"
    assignee: str = "对接人"
    assignee_status: str = "对接人状态"
    resolved_date: str = "解决日期"
    description: str = "问题描述"
    remark: str = "备注"
    remark2: str = "备注2"


@dataclass(frozen=True)
class ExcelProfile:
    canonical_fields: CanonicalFieldMapping = CanonicalFieldMapping()
    prompt_fields: tuple[str, ...] = ()
    prompt_template: str = ""
    branch_summary_fields: tuple[str, ...] = ()
```

Add `excel_profile: ExcelProfile = ExcelProfile()` to `Config`.

- [ ] **Step 4: Merge SQLite settings in `load_config`**

At the top of `config.py`, import:

```python
from bugfix_automation.storage.settings import get_settings
```

Inside `load_config`, after reading YAML and resolving `storage_db_path`, read:

```python
settings = _read_sqlite_settings(storage_db_path)
yaml_values = _merge_runtime_settings(yaml_values, settings)
```

Add helper functions near `_read_config_yaml`:

```python
def _read_sqlite_settings(db_path: Path) -> dict[str, Any]:
    try:
        return get_settings(db_path)
    except Exception:
        return {}


def _merge_runtime_settings(values: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    merged = dict(values)
    excel = settings.get("excel")
    if isinstance(excel, dict):
        for key in ("excel_path", "sheet_name", "excel_processed_status_column", "excel_processed_status_value"):
            if key in excel:
                merged[key] = excel[key]
    automation = settings.get("automation")
    if isinstance(automation, dict):
        for key in ("max_concurrency", "cli_tool"):
            if key in automation:
                merged[key] = automation[key]
        if "schedule" in automation:
            merged["schedule"] = automation["schedule"]
    for key in ("workspaces", "filters", "prompt", "branch_summary_fields", "active_workspace", "excel_profile"):
        if key in settings:
            merged[key] = settings[key]
    return merged
```

- [ ] **Step 5: Parse Excel profile**

Add:

```python
def _excel_profile(values: dict[str, Any]) -> ExcelProfile:
    raw = values.get("excel_profile")
    if not isinstance(raw, dict):
        return ExcelProfile()
    canonical = raw.get("canonical_fields")
    if not isinstance(canonical, dict):
        canonical = {}
    mapping = CanonicalFieldMapping(
        **{field: str(canonical.get(field) or getattr(CanonicalFieldMapping(), field)) for field in CanonicalFieldMapping.__dataclass_fields__}
    )
    prompt = raw.get("prompt") if isinstance(raw.get("prompt"), dict) else {}
    return ExcelProfile(
        canonical_fields=mapping,
        prompt_fields=_string_tuple(prompt.get("fields"), ()),
        prompt_template=str(prompt.get("template") or ""),
        branch_summary_fields=_string_tuple(prompt.get("branch_summary_fields"), ()),
    )
```

In `load_config`, compute:

```python
excel_profile = _excel_profile(yaml_values)
prompt_fields = excel_profile.prompt_fields or _string_tuple(prompt.get("fields"), DEFAULT_PROMPT_FIELDS)
prompt_template = excel_profile.prompt_template or str(prompt.get("template", DEFAULT_PROMPT_TEMPLATE))
branch_summary_fields = excel_profile.branch_summary_fields or _string_tuple(yaml_values.get("branch_summary_fields"), ("问题描述",))
```

Use these variables in the `Config` constructor.

- [ ] **Step 6: Run config tests**

Run: `python3 -m pytest tests/test_config.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add bugfix_automation/config.py tests/test_config.py
git commit -m "feat: merge runtime config from sqlite"
```

---

### Task 3: Save Mutable Runtime Config to SQLite

**Files:**
- Modify: `bugfix_automation/application/config_service.py`
- Modify: `bugfix_automation/application/excel_service.py`
- Modify: `bugfix_automation/application/scheduler_service.py`
- Test: `tests/test_config.py`, `tests/test_approval.py`

- [ ] **Step 1: Write failing service tests**

Update the upload test in `tests/test_approval.py` that currently patches `update_config_yaml` so it asserts SQLite setting instead:

```python
from bugfix_automation.storage.settings import get_setting

# Run this assertion immediately after calling upload_excel_from_multipart(payload, content_type).
excel_setting = get_setting(root / "data" / "app.sqlite3", "excel")
self.assertEqual(Path(excel_setting["excel_path"]).name, result["file"]["stored_name"])
```

Add to `tests/test_config.py`:

```python
from bugfix_automation.application.config_service import update_filters
from bugfix_automation.storage.settings import get_setting


def test_update_filters_writes_sqlite_settings(self) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "app.sqlite3"
        with patch.dict("os.environ", {"BUGFIX_STORAGE_DB_PATH": str(db_path)}):
            update_filters([{"field": "负责人", "op": "equals", "value": "谢浩杰"}])

        assert get_setting(db_path, "filters") == [{"field": "负责人", "op": "equals", "value": "谢浩杰"}]
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python3 -m pytest tests/test_config.py tests/test_approval.py -q`

Expected: FAIL because services still call `update_config_yaml`.

- [ ] **Step 3: Add runtime setting helpers in `config_service.py`**

Replace YAML writes with `set_setting(config.storage_db_path, key, payload)`. Keep `update_config_yaml` only for bootstrap compatibility tests.

Example for `update_filters`:

```python
from bugfix_automation.storage.settings import set_setting


def update_filters(filters: list[dict[str, Any]]) -> dict[str, Any]:
    filter_dicts = _normalized_filter_dicts(filters)
    config = load_config()
    set_setting(config.storage_db_path, "filters", filter_dicts)
    return {"ok": True, "config": config_payload(load_config())}
```

Add a helper:

```python
def _normalized_filter_dicts(filters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    filter_dicts: list[dict[str, Any]] = []
    for rule in filters:
        field = str(rule.get("field") or "").strip()
        if not field:
            continue
        op = str(rule.get("op") or "equals").strip()
        raw_values = rule.get("values") or []
        if isinstance(raw_values, str):
            raw_values = [v.strip() for v in raw_values.split(",") if v.strip()]
        single_value = str(rule.get("value") or "").strip()
        item: dict[str, Any] = {"field": field, "op": op}
        if raw_values:
            item["values"] = raw_values
        elif single_value:
            item["value"] = single_value
        filter_dicts.append(item)
    return filter_dicts
```

- [ ] **Step 4: Save Excel path in SQLite**

In `bugfix_automation/application/excel_service.py`, replace:

```python
update_config_yaml({"excel_path": target})
```

with:

```python
config = load_config()
set_setting(config.storage_db_path, "excel", {"excel_path": str(target), "sheet_name": config.sheet_name})
```

Use the same pattern in `select_excel_path`.

- [ ] **Step 5: Save schedule in SQLite**

In `bugfix_automation/application/scheduler_service.py`, replace YAML update with:

```python
from bugfix_automation.storage.settings import set_setting


def install(config: Config, hour: int, minute: int) -> dict:
    set_setting(config.storage_db_path, "automation", {"schedule": {"hour": hour, "minute": minute}})
    next_config = load_config()
    path = install_launchd_at(next_config, hour, minute)
    return {"ok": True, "plist_path": str(path), "status": launchd_status(next_config)}
```

If this would overwrite `max_concurrency` or `cli_tool`, merge with existing automation setting before setting.

- [ ] **Step 6: Run affected tests**

Run: `python3 -m pytest tests/test_config.py tests/test_approval.py tests/test_fastapi_api.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add bugfix_automation/application/config_service.py bugfix_automation/application/excel_service.py bugfix_automation/application/scheduler_service.py tests/test_config.py tests/test_approval.py
git commit -m "feat: save runtime config in sqlite"
```

---

### Task 4: Configurable BugRecord Mapping and Prompt Raw Rows

**Files:**
- Modify: `bugfix_automation/filtering.py`
- Modify: `bugfix_automation/runner.py`
- Modify: `bugfix_automation/application/bug_service.py`
- Modify: `bugfix_automation/prompt.py`
- Test: `tests/test_filtering_prompt_report.py`

- [ ] **Step 1: Write failing mapping and prompt tests**

Add to `tests/test_filtering_prompt_report.py`:

```python
from bugfix_automation.config import CanonicalFieldMapping


def test_filter_bugs_uses_custom_canonical_mapping() -> None:
    rows = [{
        "_excel_row": "9",
        "编号": "BUG-9",
        "标题": "上传按钮无反馈",
        "详情": "点击上传后没有进度",
        "负责人": "谢浩杰",
        "状态": "处理中",
    }]

    bugs = filter_bugs(
        rows,
        assignee="",
        rules=(FilterRule("负责人", "equals", "谢浩杰", ("谢浩杰",)),),
        mapping=CanonicalFieldMapping(
            issue_id="编号",
            description="标题",
            remark="详情",
            assignee="负责人",
            assignee_status="状态",
        ),
    )

    self.assertEqual(bugs[0].issue_id, "BUG-9")
    self.assertEqual(bugs[0].description, "上传按钮无反馈")
    self.assertEqual(bugs[0].remark, "点击上传后没有进度")
    self.assertEqual(bugs[0].assignee, "谢浩杰")


def test_prompt_includes_raw_excel_row_section() -> None:
    bug = filter_bugs([
        {
            "_excel_row": "2",
            "序号": "87",
            "提出人状态": "处理中",
            "来源系统": "小亦PC",
            "对接人": "谢浩杰",
            "问题描述": "账号离线状态",
            "自定义字段": "只有原始行里有",
        }
    ], assignee="谢浩杰")[0]

    prompt = render_codex_prompt(bug, target_app_path="apps/pc-web", prompt_fields=("问题描述",))

    self.assertIn("原始 Excel 行完整信息", prompt)
    self.assertIn("自定义字段: 只有原始行里有", prompt)
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python3 -m pytest tests/test_filtering_prompt_report.py -q`

Expected: FAIL because `filter_bugs` has no `mapping` parameter and prompt omits raw row section.

- [ ] **Step 3: Add `bug_record_from_row`**

In `bugfix_automation/filtering.py`, import `CanonicalFieldMapping` and add:

```python
def bug_record_from_row(row: dict[str, str], mapping: CanonicalFieldMapping | None = None) -> BugRecord:
    mapping = mapping or CanonicalFieldMapping()

    def value(field_name: str) -> str:
        header = getattr(mapping, field_name)
        return _clean(row.get(header))

    return BugRecord(
        excel_row=int(row.get("_excel_row", "0") or "0"),
        issue_id=value("issue_id") or str(row.get("_excel_row", "")),
        requester_status=value("requester_status"),
        source_system=value("source_system"),
        priority=value("priority"),
        primary_category=value("primary_category"),
        secondary_category=value("secondary_category"),
        requester=value("requester"),
        request_date=_format_excel_date(row.get(mapping.request_date)),
        assignee=value("assignee"),
        assignee_status=value("assignee_status"),
        resolved_date=_format_excel_date(row.get(mapping.resolved_date)),
        description=value("description"),
        remark=value("remark"),
        remark2=value("remark2"),
        raw=row,
    )
```

Change `filter_bugs` signature:

```python
def filter_bugs(
    rows: list[dict[str, str]],
    assignee: str,
    excluded_assignee_statuses: set[str] | None = None,
    rules: tuple[FilterRule, ...] | None = None,
    mapping: CanonicalFieldMapping | None = None,
) -> list[BugRecord]:
```

Replace the existing inline `BugRecord` constructor block with `bug_record_from_row(row, mapping)`.

- [ ] **Step 4: Pass mapping from runners/services**

In `bugfix_automation/runner.py`:

```python
return filter_bugs(rows, config.assignee, {config.excel_processed_status_value}, config.filters, config.excel_profile.canonical_fields)
```

Update any call sites that invoke `filter_bugs` from config-backed flows.

- [ ] **Step 5: Add raw row to prompt**

In `bugfix_automation/prompt.py`, build:

```python
raw_lines = "\n".join(
    f"- {field}: {value}"
    for field, value in bug.raw.items()
    if field != "_excel_row" and str(value).strip()
) or "- 无"
```

Add `raw_lines=raw_lines` to template formatting and update `prompts/fix_frontend.md`, `prompts/fix_backend.md`, and `prompts/fix_fullstack.md` with:

```text
原始 Excel 行完整信息：
{raw_lines}
```

- [ ] **Step 6: Run prompt/filter tests**

Run: `python3 -m pytest tests/test_filtering_prompt_report.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add bugfix_automation/filtering.py bugfix_automation/runner.py bugfix_automation/application/bug_service.py bugfix_automation/prompt.py prompts/fix_frontend.md prompts/fix_backend.md prompts/fix_fullstack.md tests/test_filtering_prompt_report.py
git commit -m "feat: map excel rows through profile"
```

---

### Task 5: Excel Adapter Backend API

**Files:**
- Create: `bugfix_automation/application/excel_adapter_service.py`
- Modify: `bugfix_automation/api/schemas.py`
- Modify: `bugfix_automation/api/routes/excel.py`
- Create: `prompts/excel_adapter.md`
- Test: `tests/test_excel_adapter_service.py`
- Test: `tests/test_fastapi_api.py`

- [ ] **Step 1: Write service tests**

Create `tests/test_excel_adapter_service.py`:

```python
from pathlib import Path

from bugfix_automation.application.excel_adapter_service import sanitize_adapter_suggestion
from bugfix_automation.config import Config


def test_sanitize_adapter_suggestion_drops_unknown_headers() -> None:
    suggestion = {
        "canonical_fields": {"issue_id": "编号", "description": "不存在"},
        "prompt": {"fields": ["标题", "不存在"], "template": "专用模板"},
        "branch_summary_fields": ["标题", "不存在"],
        "filters": [{"field": "状态", "op": "not_in", "values": ["已解决"]}, {"field": "不存在", "op": "equals", "value": "x"}],
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

    cleaned = sanitize_adapter_suggestion(suggestion, headers=["编号", "标题"], require_description=False)

    assert cleaned["canonical_fields"] == {"issue_id": "编号"}
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python3 -m pytest tests/test_excel_adapter_service.py -q`

Expected: FAIL because the service does not exist.

- [ ] **Step 3: Implement sanitizer and save**

Create `bugfix_automation/application/excel_adapter_service.py` with:

```python
from __future__ import annotations

import asyncio
import json
from typing import Any

from bugfix_automation.config import Config, load_config
from bugfix_automation.excel_reader import read_sheet
from bugfix_automation.storage.settings import set_setting

VALID_FILTER_OPS = {"equals", "not_equals", "in", "not_in", "any_in", "all_in", "non_empty", "empty"}
CANONICAL_KEYS = {
    "issue_id", "source_system", "priority", "primary_category", "secondary_category",
    "requester", "request_date", "requester_status", "assignee", "assignee_status",
    "resolved_date", "description", "remark", "remark2",
}


def sanitize_adapter_suggestion(
    suggestion: dict[str, Any],
    headers: list[str],
    *,
    require_description: bool = False,
) -> dict[str, Any]:
    header_set = set(headers)
    warnings = [str(item) for item in suggestion.get("warnings") or [] if str(item).strip()]
    raw_canonical = suggestion.get("canonical_fields") if isinstance(suggestion.get("canonical_fields"), dict) else {}
    canonical = {
        str(key): str(value)
        for key, value in raw_canonical.items()
        if key in CANONICAL_KEYS and str(value) in header_set
    }
    for key, value in raw_canonical.items():
        if key in CANONICAL_KEYS and str(value) and str(value) not in header_set:
            warnings.append(f"字段 {key} 指向不存在的列：{value}")
    if require_description and not canonical.get("description"):
        raise ValueError("请先选择 description 对应的 Excel 列")

    raw_prompt = suggestion.get("prompt") if isinstance(suggestion.get("prompt"), dict) else {}
    prompt_fields = [str(field) for field in raw_prompt.get("fields") or [] if str(field) in header_set]
    branch_fields = [str(field) for field in suggestion.get("branch_summary_fields") or [] if str(field) in header_set]
    filters = []
    for rule in suggestion.get("filters") or []:
        if not isinstance(rule, dict):
            continue
        field = str(rule.get("field") or "")
        op = str(rule.get("op") or "equals")
        if field not in header_set or op not in VALID_FILTER_OPS:
            continue
        item: dict[str, Any] = {"field": field, "op": op}
        values = [str(v) for v in rule.get("values") or [] if str(v).strip()]
        value = str(rule.get("value") or "").strip()
        if values:
            item["values"] = values
        elif value:
            item["value"] = value
        filters.append(item)
    return {
        "canonical_fields": canonical,
        "prompt": {"fields": prompt_fields, "template": str(raw_prompt.get("template") or "")},
        "branch_summary_fields": branch_fields,
        "filters": filters,
        "warnings": warnings,
    }
```

Add `save_excel_adapter(config, payload)` that calls sanitizer with `require_description=True`, then writes:

```python
set_setting(config.storage_db_path, "excel_profile", {
    "canonical_fields": cleaned["canonical_fields"],
    "prompt": {
        "fields": cleaned["prompt"]["fields"],
        "template": cleaned["prompt"]["template"],
        "branch_summary_fields": cleaned["branch_summary_fields"],
    },
})
set_setting(config.storage_db_path, "prompt", {
    "fields": cleaned["prompt"]["fields"],
    "template": cleaned["prompt"]["template"],
    "context_paths": list(config.prompt_context_paths),
})
set_setting(config.storage_db_path, "branch_summary_fields", cleaned["branch_summary_fields"])
if cleaned["filters"]:
    set_setting(config.storage_db_path, "filters", cleaned["filters"])
return {"ok": True, "adapter": cleaned, "config": config_payload(load_config())}
```

Import `config_payload` locally inside the function to avoid circular import at module load.

- [ ] **Step 4: Implement analyze endpoint**

Add `prompts/excel_adapter.md`:

```text
你是 Excel bug 清单适配助手。请根据表头、样例行和当前自动化配置，输出严格 JSON，不要输出解释文字。

要求：
- canonical_fields 的值必须来自表头。
- description 必须选择最能描述问题标题或问题详情的列。
- prompt.fields 只选择对修复有帮助的列。
- prompt.template 写成这张 Excel 专用的 Codex 修复补充指引。
- filters 推荐保留待处理、排除已解决/已处理、限制负责人或系统范围。

输入：
{payload_json}
```

In `excel_adapter_service.py`, implement `analyze_excel_adapter(config)`:

```python
rows = read_sheet(config.excel_path, config.sheet_name)
headers = _headers(rows)
sample_rows = rows[:3]
payload = {"headers": headers, "sample_rows": sample_rows, "workspace": config.active_workspace}
```

Call `config.cli_tool exec -` and parse stdout as JSON. Return sanitized suggestion with `require_description=False`.

- [ ] **Step 5: Add API routes**

In `bugfix_automation/api/schemas.py`:

```python
class ExcelAdapterSaveRequest(BaseModel):
    adapter: dict[str, Any] = {}
```

In `bugfix_automation/api/routes/excel.py`:

```python
from bugfix_automation.application.excel_adapter_service import analyze_excel_adapter, save_excel_adapter
from bugfix_automation.api.schemas import ExcelAdapterSaveRequest
from bugfix_automation.api.dependencies import get_config
from bugfix_automation.config import Config


@router.post("/api/excel/adapter/analyze")
async def post_excel_adapter_analyze(config: Config = Depends(get_config)):
    return await analyze_excel_adapter(config)


@router.post("/api/excel/adapter/save")
def post_excel_adapter_save(payload: ExcelAdapterSaveRequest, config: Config = Depends(get_config)):
    return save_excel_adapter(config, payload.adapter)
```

- [ ] **Step 6: Run backend adapter tests**

Run: `python3 -m pytest tests/test_excel_adapter_service.py tests/test_fastapi_api.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add bugfix_automation/application/excel_adapter_service.py bugfix_automation/api/schemas.py bugfix_automation/api/routes/excel.py prompts/excel_adapter.md tests/test_excel_adapter_service.py tests/test_fastapi_api.py
git commit -m "feat: add excel adapter api"
```

---

### Task 6: Frontend Adapter UI

**Files:**
- Modify: `approval-web/src/features/approval/types.ts`
- Modify: `approval-web/src/features/approval/hooks/useApprovalDashboard.ts`
- Create: `approval-web/src/features/approval/components/ExcelAdapterPanel.tsx`
- Modify: `approval-web/app/page.tsx`

- [ ] **Step 1: Add TypeScript types**

In `approval-web/src/features/approval/types.ts`, add:

```ts
export type ExcelProfile = {
  canonical_fields: Record<string, string>;
  prompt: {
    fields: string[];
    template: string;
    branch_summary_fields: string[];
  };
};

export type ExcelAdapterSuggestion = {
  canonical_fields: Record<string, string>;
  prompt: {
    fields: string[];
    template: string;
  };
  branch_summary_fields: string[];
  filters: FilterRule[];
  warnings: string[];
};
```

Add `excel_profile: ExcelProfile;` to `ConfigPayload`.

- [ ] **Step 2: Expose hook actions**

In `useApprovalDashboard.ts`, import `ExcelAdapterSuggestion` and add state:

```ts
const [excelAdapter, setExcelAdapter] = useState<ExcelAdapterSuggestion | null>(null);
```

Add actions:

```ts
const analyzeExcelAdapter = async () => {
  setBusyAction("/api/excel/adapter/analyze");
  setToast("");
  try {
    const data = await fetchJson<{ ok: boolean; adapter: ExcelAdapterSuggestion }>("/api/excel/adapter/analyze", { method: "POST" });
    setExcelAdapter(data.adapter);
    setToast("Excel 识别完成，请检查后保存");
  } catch (error) {
    setToast(error instanceof Error ? error.message : "识别失败");
  } finally {
    setBusyAction("");
  }
};

const saveExcelAdapter = async (adapter: ExcelAdapterSuggestion) => {
  await postAction("/api/excel/adapter/save", { adapter }, "Excel 适配配置已保存");
  setExcelAdapter(null);
};
```

Return `excelAdapter`, `setExcelAdapter`, `analyzeExcelAdapter`, and `saveExcelAdapter`.

- [ ] **Step 3: Create adapter panel**

Create `approval-web/src/features/approval/components/ExcelAdapterPanel.tsx`:

```tsx
import { Loader2, Save, Sparkles } from "lucide-react";
import type { ExcelAdapterSuggestion } from "../types";

type Props = {
  adapter: ExcelAdapterSuggestion | null;
  busy: boolean;
  onAnalyze: () => void;
  onChange: (adapter: ExcelAdapterSuggestion) => void;
  onSave: (adapter: ExcelAdapterSuggestion) => void;
};

export function ExcelAdapterPanel({ adapter, busy, onAnalyze, onChange, onSave }: Props) {
  const updateTemplate = (template: string) => {
    if (!adapter) return;
    onChange({ ...adapter, prompt: { ...adapter.prompt, template } });
  };

  return (
    <div className="configField">
      <label className="configLabel">Excel 智能适配</label>
      <button className="buttonSmall secondary" disabled={busy} onClick={onAnalyze}>
        {busy ? <Loader2 size={13} className="spin" /> : <Sparkles size={13} />}
        AI 识别 Excel
      </button>
      {adapter ? (
        <div className="adapterPreview">
          {adapter.warnings.length ? <div className="filterEditorError">{adapter.warnings.join("；")}</div> : null}
          <pre className="promptContent">{JSON.stringify(adapter.canonical_fields, null, 2)}</pre>
          <textarea
            className="configTextarea"
            value={adapter.prompt.template}
            onChange={event => updateTemplate(event.target.value)}
            rows={4}
          />
          <button className="buttonSmall secondary" onClick={() => onSave(adapter)}>
            <Save size={13} />保存适配配置
          </button>
        </div>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 4: Place panel in page**

In `approval-web/app/page.tsx`, import the component and destructure hook values. Place inside the `AI 提示词` section above `传给 AI 的 Excel 列`:

```tsx
<ExcelAdapterPanel
  adapter={excelAdapter}
  busy={busyAction === "/api/excel/adapter/analyze"}
  onAnalyze={() => void analyzeExcelAdapter()}
  onChange={setExcelAdapter}
  onSave={(adapter) => void saveExcelAdapter(adapter)}
/>
```

- [ ] **Step 5: Run TypeScript check**

Run: `cd approval-web && npm run typecheck`

If the project has no `typecheck` script, run: `cd approval-web && npm run build`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add approval-web/src/features/approval/types.ts approval-web/src/features/approval/hooks/useApprovalDashboard.ts approval-web/src/features/approval/components/ExcelAdapterPanel.tsx approval-web/app/page.tsx
git commit -m "feat: add excel adapter ui"
```

---

### Task 7: Persist Mapped Import Summaries

**Files:**
- Modify: `bugfix_automation/storage/repositories.py`
- Modify: `bugfix_automation/application/excel_service.py`
- Test: `tests/test_excel_storage.py`

- [ ] **Step 1: Write failing mapped storage test**

Add to `tests/test_excel_storage.py`:

```python
from bugfix_automation.config import CanonicalFieldMapping


def test_save_excel_import_uses_canonical_mapping(tmp_path: Path):
    db_path = tmp_path / "app.sqlite3"
    excel_path = tmp_path / "bugs.xlsx"
    excel_path.write_bytes(b"fake-xlsx-bytes")

    save_excel_import(
        db_path,
        original_filename="bugs.xlsx",
        stored_path=excel_path,
        sheet_name="Sheet1",
        rows=[{"_excel_row": "5", "编号": "A-5", "标题": "按钮错位", "负责人": "谢浩杰", "状态": "处理中"}],
        config_snapshot_id=None,
        mapping=CanonicalFieldMapping(issue_id="编号", description="标题", assignee="负责人", assignee_status="状态"),
    )

    with sqlite3.connect(db_path) as db:
        row = db.execute("SELECT issue_id, description, assignee, assignee_status FROM excel_import_rows").fetchone()

    assert row == ("A-5", "按钮错位", "谢浩杰", "处理中")
```

- [ ] **Step 2: Run test to verify failure**

Run: `python3 -m pytest tests/test_excel_storage.py -q`

Expected: FAIL because `save_excel_import` does not accept `mapping`.

- [ ] **Step 3: Update repository function**

In `bugfix_automation/storage/repositories.py`, change signature:

```python
def save_excel_import(
    db_path: Path,
    *,
    original_filename: str,
    stored_path: Path,
    sheet_name: str,
    rows: list[dict[str, Any]],
    config_snapshot_id: str | None,
    mapping: CanonicalFieldMapping | None = None,
) -> str:
```

Use:

```python
mapping = mapping or CanonicalFieldMapping()
issue_id = str(row.get(mapping.issue_id) or "")
description = str(row.get(mapping.description) or "")
assignee = str(row.get(mapping.assignee) or "")
requester_status = str(row.get(mapping.requester_status) or "")
assignee_status = str(row.get(mapping.assignee_status) or "")
```

- [ ] **Step 4: Pass mapping from excel service**

In `_record_excel_import`, pass:

```python
mapping=config.excel_profile.canonical_fields,
```

- [ ] **Step 5: Run Excel storage tests**

Run: `python3 -m pytest tests/test_excel_storage.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add bugfix_automation/storage/repositories.py bugfix_automation/application/excel_service.py tests/test_excel_storage.py
git commit -m "feat: store mapped excel import summaries"
```

---

### Task 8: Full Verification and Documentation

**Files:**
- Modify: `README.md`
- Optional Modify: `docs/superpowers/specs/2026-05-21-excel-ai-adapter-design.md` only if implementation discovers a required correction.

- [ ] **Step 1: Update README configuration section**

Change the config section to say:

```markdown
`config.yaml` 现在主要作为启动配置和本机兜底配置。审批台里修改的 Excel、筛选规则、prompt、工作区和 AI 识别出的 Excel 适配信息会保存到 SQLite：`data/app.sqlite3`。

配置读取顺序：

```text
环境变量 > SQLite 当前配置 > config.yaml > 代码默认值
```
```

Keep the old YAML example but label it as “首次启动或兜底配置”.

- [ ] **Step 2: Run backend tests**

Run:

```bash
python3 -m pytest tests/test_config.py tests/test_excel_storage.py tests/test_filtering_prompt_report.py tests/test_excel_adapter_service.py tests/test_fastapi_api.py -q
```

Expected: PASS.

- [ ] **Step 3: Run frontend build or typecheck**

Run:

```bash
cd approval-web && npm run build
```

Expected: PASS.

- [ ] **Step 4: Run full test suite if targeted tests pass**

Run:

```bash
python3 -m pytest -q
```

Expected: PASS.

- [ ] **Step 5: Commit docs and verification fixes**

```bash
git add README.md docs/superpowers/specs/2026-05-21-excel-ai-adapter-design.md
git commit -m "docs: document sqlite runtime config"
```

If there are no doc changes beyond README, commit only README.

---

## Self-Review

- Spec coverage: Tasks 1-3 implement SQLite runtime configuration and config precedence. Task 4 implements canonical row mapping and prompt raw row inclusion. Task 5 implements AI adapter backend. Task 6 implements the front-end entry point. Task 7 keeps import history aligned with mappings. Task 8 verifies and documents the new model.
- Placeholder scan: This plan contains no `TBD`, no unfilled TODOs, and every code-changing task includes concrete snippets or commands.
- Type consistency: `ExcelProfile`, `CanonicalFieldMapping`, `excel_profile`, `canonical_fields`, `prompt.fields`, `prompt.template`, and `branch_summary_fields` are used consistently across backend config, API payloads, and frontend types.
