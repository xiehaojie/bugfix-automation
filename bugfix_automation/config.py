from __future__ import annotations

from dataclasses import dataclass
import json
import os
import sqlite3
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FilterRule:
    field: str
    op: str
    value: str = ""
    values: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkspaceConfig:
    id: str
    name: str
    target_repo: Path
    target_app_path: str
    scope_paths: tuple[str, ...]
    verify_commands: tuple[tuple[str, ...], ...]
    prompt_context_paths: tuple[str, ...]
    max_concurrency: int
    scope: str = "frontend"
    repo_paths: tuple[Path, ...] = ()


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


@dataclass(frozen=True)
class Config:
    excel_path: Path
    sheet_name: str
    assignee: str
    target_repo: Path
    target_app_path: str
    worktree_root: Path
    runs_root: Path
    logs_root: Path
    launchd_label: str
    cli_tool: str
    schedule_hour: int
    schedule_minute: int
    approval_web_port: int
    approval_api_port: int
    data_root: Path = Path("data")
    storage_db_path: Path = Path("data/app.sqlite3")
    excel_processed_status_column: str = "对接人状态"
    excel_processed_status_value: str = "已处理"
    active_workspace: str = "pc-web"
    workspaces: tuple[WorkspaceConfig, ...] = ()
    filters: tuple[FilterRule, ...] = ()
    branch_summary_fields: tuple[str, ...] = ()
    prompt_fields: tuple[str, ...] = ()
    prompt_template: str = ""
    prompt_context_paths: tuple[str, ...] = ()
    max_concurrency: int = 2
    validation_target_branches: tuple[str, ...] = ("main", "master", "develop")
    excel_profile: ExcelProfile = ExcelProfile()


def load_config(config_path: Path | None = None) -> Config:
    repo_root = repo_root_path()
    yaml_path = config_path or default_config_path()
    yaml_values = _read_config_yaml(yaml_path)
    bootstrap_data_root = _path(os.environ.get("BUGFIX_DATA_ROOT", yaml_values.get("data_root", repo_root / "data")), repo_root)
    bootstrap_db_path = _path(
        os.environ.get("BUGFIX_STORAGE_DB_PATH", yaml_values.get("storage_db_path", bootstrap_data_root / "app.sqlite3")),
        repo_root,
    )
    yaml_values = _merge_runtime_settings(yaml_values, _read_sqlite_settings(bootstrap_db_path))

    def value(key: str, env_name: str, default: Any) -> Any:
        if env_name in os.environ:
            return os.environ[env_name]
        return yaml_values.get(key, default)

    target_repo = _path(value("target_repo", "BUGFIX_TARGET_REPO", "/Users/xiehaojie/code/monorepo"), repo_root)
    schedule = yaml_values.get("schedule", {})
    active_workspace = str(value("active_workspace", "BUGFIX_ACTIVE_WORKSPACE", "pc-web"))
    worktree_root = _path(value("worktree_root", "BUGFIX_WORKTREE_ROOT", repo_root / ".target-worktrees"), repo_root)
    runs_root = _path(value("runs_root", "BUGFIX_RUNS_ROOT", repo_root / "runs"), repo_root)
    logs_root = _path(value("logs_root", "BUGFIX_LOGS_ROOT", repo_root / "logs"), repo_root)
    data_root = _path(value("data_root", "BUGFIX_DATA_ROOT", repo_root / "data"), repo_root)
    storage_db_path = _path(value("storage_db_path", "BUGFIX_STORAGE_DB_PATH", data_root / "app.sqlite3"), repo_root)
    fallback_app_path = str(value("target_app_path", "BUGFIX_TARGET_APP_PATH", "apps/pc-web"))
    workspaces = _workspace_configs(yaml_values, repo_root, target_repo, fallback_app_path)
    active = _active_workspace(workspaces, active_workspace) if workspaces else None
    filters = _filter_rules(yaml_values, str(value("assignee", "BUGFIX_ASSIGNEE", "谢浩杰")))
    prompt = yaml_values.get("prompt", {})
    if not isinstance(prompt, dict):
        prompt = {}
    excel_profile = _excel_profile(yaml_values.get("excel_profile"))
    branch_summary_fields = excel_profile.branch_summary_fields or _string_tuple(
        yaml_values.get("branch_summary_fields"), ("问题描述",)
    )
    global_max_concurrency = int(value("max_concurrency", "BUGFIX_MAX_CONCURRENCY", active.max_concurrency if active else 2))
    return Config(
        excel_path=_path(value("excel_path", "BUGFIX_EXCEL_PATH", "/Users/xiehaojie/Desktop/亦城数智人在线清单.xlsx"), repo_root),
        sheet_name=str(value("sheet_name", "BUGFIX_SHEET_NAME", "在线问题清单")),
        assignee=str(value("assignee", "BUGFIX_ASSIGNEE", "谢浩杰")),
        target_repo=active.target_repo if active else target_repo,
        target_app_path=active.target_app_path if active else fallback_app_path,
        worktree_root=worktree_root,
        runs_root=runs_root,
        logs_root=logs_root,
        data_root=data_root,
        storage_db_path=storage_db_path,
        launchd_label=str(value("launchd_label", "BUGFIX_LAUNCHD_LABEL", "local.bugfix-automation.nightly")),
        cli_tool=str(value("cli_tool", "BUGFIX_CLI_TOOL", value("codex_bin", "BUGFIX_CODEX_BIN", "codex"))),
        schedule_hour=int(value("schedule_hour", "BUGFIX_SCHEDULE_HOUR", schedule.get("hour", 22))),
        schedule_minute=int(value("schedule_minute", "BUGFIX_SCHEDULE_MINUTE", schedule.get("minute", 0))),
        approval_web_port=int(value("approval_web_port", "BUGFIX_APPROVAL_WEB_PORT", 8765)),
        approval_api_port=int(value("approval_api_port", "BUGFIX_APPROVAL_API_PORT", 8766)),
        excel_processed_status_column=str(value("excel_processed_status_column", "BUGFIX_EXCEL_PROCESSED_STATUS_COLUMN", "对接人状态")),
        excel_processed_status_value=str(value("excel_processed_status_value", "BUGFIX_EXCEL_PROCESSED_STATUS_VALUE", "已处理")),
        active_workspace=active.id if active else "",
        workspaces=workspaces,
        filters=filters,
        branch_summary_fields=branch_summary_fields,
        prompt_fields=excel_profile.prompt_fields or _string_tuple(prompt.get("fields"), DEFAULT_PROMPT_FIELDS),
        prompt_template=excel_profile.prompt_template or str(prompt.get("template", DEFAULT_PROMPT_TEMPLATE)),
        prompt_context_paths=(*_string_tuple(prompt.get("context_paths"), ()), *(active.prompt_context_paths if active else ())),
        max_concurrency=max(1, min(int(os.environ.get("BUGFIX_MAX_CONCURRENCY", global_max_concurrency)), 8)),
        validation_target_branches=_string_tuple(value("validation_target_branches", "BUGFIX_VALIDATION_TARGET_BRANCHES", ("main", "master", "develop"))),
        excel_profile=excel_profile,
    )


def repo_root_path() -> Path:
    return Path(__file__).resolve().parents[1]


def default_config_path() -> Path:
    return repo_root_path() / "config.yaml"


def _read_sqlite_settings(db_path: Path) -> dict[str, Any]:
    if not db_path.exists():
        return {}

    try:
        with sqlite3.connect(db_path) as db:
            db.row_factory = sqlite3.Row
            rows = db.execute("SELECT key, value_json FROM app_settings").fetchall()
    except Exception:
        return {}

    settings: dict[str, Any] = {}
    for row in rows:
        try:
            settings[str(row["key"])] = json.loads(str(row["value_json"]))
        except Exception:
            settings[str(row["key"])] = None
    return settings


def _merge_runtime_settings(yaml_values: dict[str, Any], sqlite_settings: dict[str, Any]) -> dict[str, Any]:
    merged = dict(yaml_values)
    if not sqlite_settings:
        return merged

    excel_settings = sqlite_settings.get("excel")
    if isinstance(excel_settings, dict):
        for key in ("excel_path", "sheet_name", "excel_processed_status_column", "excel_processed_status_value"):
            if key in excel_settings:
                merged[key] = excel_settings[key]

    automation_settings = sqlite_settings.get("automation")
    if isinstance(automation_settings, dict):
        for key in (
            "max_concurrency",
            "launchd_label",
            "cli_tool",
            "codex_bin",
            "schedule",
            "schedule_hour",
            "schedule_minute",
            "approval_web_port",
            "approval_api_port",
            "validation_target_branches",
        ):
            if key in automation_settings:
                merged[key] = automation_settings[key]

    excel_profile_settings = sqlite_settings.get("excel_profile")
    if isinstance(excel_profile_settings, dict):
        merged["excel_profile"] = excel_profile_settings
        profile_prompt = excel_profile_settings.get("prompt")
        if isinstance(profile_prompt, dict):
            merged["prompt"] = _merge_mapping(merged.get("prompt"), profile_prompt, ("fields", "template", "context_paths"))
            if "branch_summary_fields" in profile_prompt:
                merged["branch_summary_fields"] = profile_prompt["branch_summary_fields"]

    if "workspaces" in sqlite_settings:
        merged["workspaces"] = sqlite_settings["workspaces"]
    if "filters" in sqlite_settings:
        merged["filters"] = sqlite_settings["filters"]
    if "active_workspace" in sqlite_settings:
        merged["active_workspace"] = sqlite_settings["active_workspace"]

    prompt_settings = sqlite_settings.get("prompt")
    if isinstance(prompt_settings, dict):
        merged["prompt"] = _merge_mapping(merged.get("prompt"), prompt_settings, ("fields", "template", "context_paths"))
    if "branch_summary_fields" in sqlite_settings:
        merged["branch_summary_fields"] = sqlite_settings["branch_summary_fields"]

    return merged


def _merge_mapping(base: Any, updates: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    merged = dict(base) if isinstance(base, dict) else {}
    for key in keys:
        if key in updates:
            merged[key] = updates[key]
    return merged


def _excel_profile(value: Any) -> ExcelProfile:
    if not isinstance(value, dict):
        return ExcelProfile()

    raw_canonical_fields = value.get("canonical_fields")
    if not isinstance(raw_canonical_fields, dict):
        raw_canonical_fields = {}
    default_mapping = CanonicalFieldMapping()
    canonical_kwargs: dict[str, str] = {}
    for field_name in CanonicalFieldMapping.__dataclass_fields__:
        default_value = getattr(default_mapping, field_name)
        raw_value = raw_canonical_fields.get(field_name, default_value)
        text = str(raw_value).strip() if raw_value is not None else ""
        canonical_kwargs[field_name] = text or default_value

    prompt = value.get("prompt")
    if not isinstance(prompt, dict):
        prompt = {}

    return ExcelProfile(
        canonical_fields=CanonicalFieldMapping(**canonical_kwargs),
        prompt_fields=_string_tuple(prompt.get("fields"), ()),
        prompt_template=str(prompt.get("template", "")) if prompt.get("template") is not None else "",
        branch_summary_fields=_string_tuple(prompt.get("branch_summary_fields"), ()),
    )


def update_config_yaml(updates: dict[str, Any], config_path: Path | None = None) -> None:
    path = config_path or default_config_path()
    existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    lines = _update_yaml_lines(existing, updates)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _path(raw: Any, repo_root: Path) -> Path:
    path = Path(str(raw)).expanduser()
    if path.is_absolute():
        return path
    return repo_root / path


def _read_config_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return _parse_yaml_subset(path.read_text(encoding="utf-8").splitlines())


def _parse_scalar(value: str) -> str | int | bool | list:
    if value == "[]":
        return []
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    if value.isdigit():
        return int(value)
    if "," in value:
        return [part.strip() for part in value.split(",") if part.strip()]
    return value


def _update_yaml_lines(lines: list[str], updates: dict[str, Any]) -> list[str]:
    next_lines = list(lines)
    for key, value in updates.items():
        if isinstance(value, dict):
            next_lines = _set_yaml_section(next_lines, key, value)
        elif isinstance(value, list):
            next_lines = _set_yaml_top_list(next_lines, key, value)
        else:
            next_lines = _set_yaml_scalar(next_lines, key, value)
    return next_lines


def _set_yaml_top_list(lines: list[str], key: str, value: list) -> list[str]:
    """Replace a top-level list section in YAML (e.g. filters)."""
    key_index: int | None = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or line.startswith(" "):
            continue
        current_key = line.split(":", 1)[0].strip()
        if current_key == key:
            key_index = i
            break
    rendered = _render_yaml_field(key, value, 0)
    if key_index is None:
        return [*lines, "", *rendered]
    end_index = len(lines)
    for i in range(key_index + 1, len(lines)):
        if lines[i].strip() and not lines[i].startswith(" "):
            end_index = i
            break
    return [*lines[:key_index], *rendered, *lines[end_index:]]


def _set_yaml_scalar(lines: list[str], key: str, value: Any) -> list[str]:
    rendered = f"{key}: {_render_yaml_scalar(value)}"
    for index, raw_line in enumerate(lines):
        stripped = raw_line.strip()
        if raw_line.startswith(" ") or stripped.startswith("#") or ":" not in raw_line:
            continue
        current_key = raw_line.split(":", 1)[0].strip()
        if current_key == key:
            lines[index] = rendered
            return lines
    return [*lines, rendered]


def _set_yaml_section(lines: list[str], section: str, values: dict[str, Any]) -> list[str]:
    section_index = None
    for index, raw_line in enumerate(lines):
        if not raw_line.startswith(" ") and raw_line.strip() == f"{section}:":
            section_index = index
            break
    if section_index is None:
        return [*lines, f"{section}:", *[f"  {key}: {_render_yaml_scalar(value)}" for key, value in values.items()]]

    end_index = len(lines)
    for index in range(section_index + 1, len(lines)):
        if lines[index].strip() and not lines[index].startswith(" "):
            end_index = index
            break

    section_lines = lines[section_index + 1 : end_index]
    for key, value in values.items():
        rendered_lines = _render_yaml_field(key, value, 2)
        replaced = False
        offset = 0
        while offset < len(section_lines):
            raw_line = section_lines[offset]
            if raw_line.startswith(" ") and raw_line.split(":", 1)[0].strip() == key:
                remove_until = offset + 1
                while remove_until < len(section_lines):
                    next_line = section_lines[remove_until]
                    if next_line.strip() and len(next_line) - len(next_line.lstrip(" ")) <= 2:
                        break
                    remove_until += 1
                section_lines[offset:remove_until] = rendered_lines
                replaced = True
                break
            offset += 1
        if not replaced:
            section_lines.extend(rendered_lines)
    return [*lines[: section_index + 1], *section_lines, *lines[end_index:]]


def _render_yaml_scalar(value: Any) -> str:
    text = str(value)
    if any(char in text for char in ["#", "\n"]) or text.strip() != text:
        return repr(text)
    return text


def _render_yaml_field(key: str, value: Any, indent: int = 0) -> list[str]:
    prefix = " " * indent
    if isinstance(value, dict):
        lines = [f"{prefix}{key}:"]
        for child_key, child_value in value.items():
            lines.extend(_render_yaml_field(str(child_key), child_value, indent + 2))
        return lines
    if isinstance(value, (list, tuple)):
        if not value:
            return [f"{prefix}{key}: []"]
        lines = [f"{prefix}{key}:"]
        for item in value:
            if isinstance(item, dict):
                item_lines = []
                for child_key, child_value in item.items():
                    item_lines.extend(_render_yaml_field(str(child_key), child_value, indent + 4))
                if item_lines:
                    first = item_lines[0]
                    lines.append(f"{' ' * (indent + 2)}- {first.lstrip()}")
                    lines.extend(item_lines[1:])
            else:
                lines.append(f"{' ' * (indent + 2)}- {_render_yaml_scalar(item)}")
        return lines
    return [f"{prefix}{key}: {_render_yaml_scalar(value)}"]


DEFAULT_PROMPT_FIELDS = (
    "序号",
    "来源系统",
    "一级分类",
    "二级分类",
    "优先级",
    "提出人",
    "提出日期",
    "提出人状态",
    "对接人",
    "对接人状态",
    "解决日期",
    "问题描述",
    "备注",
    "备注2",
)

DEFAULT_PROMPT_TEMPLATE = """请按下面流程修复：
1. 先阅读 Excel 选中字段、截图和工程上下文路径，确认问题是否属于当前前端工作区。
2. 只修改允许的前端目录；不要修改后端、接口服务、数据库、部署配置。
3. 如果判断必须依赖后端或数据改造，请停止并在最终说明中写清原因。
4. 修复后运行当前工作区配置的检查命令；如果依赖缺失或命令失败，请保留失败原因。
5. 不要 push，不要合并主分支，不要执行破坏性 git 命令。"""


def _workspace_configs(values: dict[str, Any], repo_root: Path, fallback_repo: Path, fallback_app: str) -> tuple[WorkspaceConfig, ...]:
    has_workspaces_key = "workspaces" in values
    raw_workspaces = values.get("workspaces")
    if not isinstance(raw_workspaces, list):
        raw_workspaces = []
    parsed: list[WorkspaceConfig] = []
    for index, item in enumerate(raw_workspaces):
        if not isinstance(item, dict):
            continue
        workspace_id = str(item.get("id") or f"workspace-{index + 1}")
        target_app_path = str(item.get("target_app_path") or fallback_app)
        raw_repos = item.get("repo_paths") or item.get("target_repo") or fallback_repo
        if isinstance(raw_repos, list):
            repo_paths = tuple(_path(r, repo_root) for r in raw_repos if r)
        else:
            repo_paths = (_path(raw_repos, repo_root),)
        primary_repo = repo_paths[0] if repo_paths else _path(fallback_repo, repo_root)
        parsed.append(
            WorkspaceConfig(
                id=workspace_id,
                name=str(item.get("name") or workspace_id),
                target_repo=primary_repo,
                target_app_path=target_app_path,
                scope_paths=_string_tuple(item.get("scope_paths"), (target_app_path,)),
                verify_commands=_command_tuple(item.get("verify_commands")),
                prompt_context_paths=_string_tuple(item.get("prompt_context_paths"), ()),
                max_concurrency=int(item.get("max_concurrency") or values.get("max_concurrency") or 2),
                scope=str(item.get("scope") or "frontend"),
                repo_paths=repo_paths,
            )
        )
    if parsed:
        return tuple(parsed)
    # Only fall back to the default workspace if the key was never written to YAML.
    # If the key is present but empty (user deleted all workspaces), return empty tuple.
    if has_workspaces_key:
        return ()
    return (
        WorkspaceConfig(
            id="pc-web",
            name="PC Web",
            target_repo=fallback_repo,
            target_app_path=fallback_app,
            scope_paths=(fallback_app,),
            verify_commands=(),
            prompt_context_paths=(),
            max_concurrency=int(values.get("max_concurrency") or 2),
        ),
    )


def _active_workspace(workspaces: tuple[WorkspaceConfig, ...], active_workspace: str) -> WorkspaceConfig:
    for workspace in workspaces:
        if workspace.id == active_workspace:
            return workspace
    return workspaces[0]


def active_workspace_config(config: Config) -> WorkspaceConfig:
    return _active_workspace(config.workspaces, config.active_workspace)


def _filter_rules(values: dict[str, Any], assignee: str) -> tuple[FilterRule, ...]:
    raw_filters = values.get("filters")
    rules: list[FilterRule] = []
    if isinstance(raw_filters, list):
        for item in raw_filters:
            if not isinstance(item, dict):
                continue
            field = str(item.get("field", "")).strip()
            if not field:
                continue
            raw_values = item.get("values")
            value = str(item.get("value", "")).strip()
            rules.append(
                FilterRule(
                    field=field,
                    op=str(item.get("op", "equals")).strip() or "equals",
                    value=value,
                    values=_string_tuple(raw_values, (value,) if value else ()),
                )
            )
    if rules:
        return tuple(rules)
    return (
        FilterRule("对接人", "equals", assignee, (assignee,)),
        FilterRule("对接人状态", "not_in", values=("已解决", str(values.get("excel_processed_status_value", "已处理")))),
        FilterRule("来源系统", "in", values=("小亦PC", "小亦APP")),
        FilterRule("提出人状态", "in", values=("待处理", "处理中")),
    )



def _string_tuple(value: Any, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    if value is None:
        return default
    if isinstance(value, str):
        return tuple(part.strip() for part in value.split(",") if part.strip())
    if isinstance(value, (list, tuple)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return default


def _command_tuple(value: Any) -> tuple[tuple[str, ...], ...]:
    if value is None or value == "" or value == []:
        return ()
    if not isinstance(value, list):
        # Accept comma-separated string for back-compat
        if isinstance(value, str):
            parts = [p.strip() for p in value.split(",") if p.strip()]
            value = parts
        else:
            return ()
    commands: list[tuple[str, ...]] = []
    for item in value:
        if isinstance(item, str):
            parts = tuple(part for part in item.split(" ") if part)
            if parts:
                commands.append(parts)
        elif isinstance(item, list):
            parts = tuple(str(part) for part in item if str(part))
            if parts:
                commands.append(parts)
    return tuple(commands)


def _parse_yaml_subset(lines: list[str]) -> dict[str, Any]:
    root: dict[str, Any] = {}
    index = 0
    while index < len(lines):
        raw = _strip_comment(lines[index])
        if not raw.strip():
            index += 1
            continue
        if raw.startswith(" "):
            index += 1
            continue
        key, raw_value = _split_key_value(raw)
        if key is None:
            index += 1
            continue
        if raw_value:
            root[key] = _parse_scalar(raw_value)
            index += 1
            continue
        block, index = _parse_block(lines, index + 1, 2)
        root[key] = block
    return root


def _parse_block(lines: list[str], index: int, indent: int) -> tuple[Any, int]:
    items: list[Any] = []
    mapping: dict[str, Any] = {}
    mode: str | None = None
    while index < len(lines):
        raw = _strip_comment(lines[index]).rstrip()
        if not raw.strip():
            index += 1
            continue
        current_indent = len(raw) - len(raw.lstrip(" "))
        if current_indent < indent:
            break
        text = raw[indent:]
        if text.startswith("- "):
            mode = "list"
            item_text = text[2:].strip()
            if ":" in item_text:
                key, raw_value = _split_key_value(item_text)
                item: dict[str, Any] = {}
                if key is not None:
                    item[key] = _parse_scalar(raw_value) if raw_value else ""
                index += 1
                while index < len(lines):
                    child = _strip_comment(lines[index]).rstrip()
                    if not child.strip():
                        index += 1
                        continue
                    child_indent = len(child) - len(child.lstrip(" "))
                    if child_indent <= current_indent:
                        break
                    child_text = child[child_indent:]
                    child_key, child_value = _split_key_value(child_text)
                    if child_key is None:
                        index += 1
                        continue
                    if child_value:
                        item[child_key] = _parse_scalar(child_value)
                        index += 1
                    else:
                        nested, index = _parse_block(lines, index + 1, child_indent + 2)
                        item[child_key] = nested
                items.append(item)
            else:
                items.append(_parse_scalar(item_text))
                index += 1
            continue
        mode = "dict"
        key, raw_value = _split_key_value(text)
        if key is not None:
            if raw_value:
                mapping[key] = _parse_scalar(raw_value)
                index += 1
            else:
                nested, index = _parse_block(lines, index + 1, indent + 2)
                mapping[key] = nested
        else:
            index += 1
    return (items if mode == "list" else mapping), index


def _strip_comment(line: str) -> str:
    if "#" not in line:
        return line.rstrip()
    quote: str | None = None
    for index, char in enumerate(line):
        if char in {"'", '"'}:
            quote = None if quote == char else char
        elif char == "#" and quote is None:
            return line[:index].rstrip()
    return line.rstrip()


def _split_key_value(text: str) -> tuple[str | None, str]:
    if ":" not in text:
        return None, ""
    key, raw_value = text.split(":", 1)
    return key.strip(), raw_value.strip()
