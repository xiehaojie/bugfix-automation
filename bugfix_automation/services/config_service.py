from __future__ import annotations

from pathlib import Path
from typing import Any

from bugfix_automation.domain.capability_system import capability_status
from bugfix_automation.config import Config, WorkspaceConfig, load_config
from bugfix_automation.infra.file_metadata import file_metadata
from bugfix_automation.storage.settings import get_setting, set_setting


def config_payload(config: Config) -> dict[str, Any]:
    return {
        "target_repo": str(config.target_repo),
        "target_app_path": config.target_app_path,
        "excel_path": str(config.excel_path),
        "excel_file": file_metadata(config.excel_path) if config.excel_path.exists() else {},
        "assignee": config.assignee,
        "web_port": config.approval_web_port,
        "api_port": config.approval_api_port,
        "active_workspace": config.active_workspace,
        "max_concurrency": config.max_concurrency,
        "cli_tool": config.cli_tool,
        "workspaces": [
            {
                "id": workspace.id,
                "name": workspace.name,
                "target_repo": str(workspace.target_repo),
                "target_app_path": workspace.target_app_path,
                "scope_paths": list(workspace.scope_paths),
                "verify_commands": [" ".join(command) for command in workspace.verify_commands],
                "prompt_context_paths": list(workspace.prompt_context_paths),
                "max_concurrency": workspace.max_concurrency,
                "scope": workspace.scope,
                "repo_paths": [str(p) for p in workspace.repo_paths],
            }
            for workspace in config.workspaces
        ],
        "filters": [
            {"field": rule.field, "op": rule.op, "value": rule.value, "values": list(rule.values)}
            for rule in config.filters
        ],
        "branch_summary_fields": list(config.branch_summary_fields),
        "capability_status": capability_status(config),
        "prompt": {
            "fields": list(config.prompt_fields),
            "template": config.prompt_template,
            "context_paths": list(config.prompt_context_paths),
        },
    }


def select_workspace(config: Config, workspace_id: str) -> dict[str, Any]:
    if not any(workspace.id == workspace_id for workspace in config.workspaces):
        raise ValueError(f"未知工作区: {workspace_id}")
    set_setting(config.storage_db_path, "active_workspace", workspace_id)
    return {"ok": True, "config": config_payload(load_config())}


def update_automation_config(payload: dict[str, Any]) -> dict[str, Any]:
    config = load_config()
    automation = get_setting(config.storage_db_path, "automation", {})
    if not isinstance(automation, dict):
        automation = {}
    automation_updates: dict[str, Any] = {}
    if "max_concurrency" in payload:
        automation_updates["max_concurrency"] = int(payload["max_concurrency"])
    if "branch_summary_fields" in payload:
        set_setting(config.storage_db_path, "branch_summary_fields", payload["branch_summary_fields"])
    if "prompt" in payload and isinstance(payload["prompt"], dict):
        set_setting(config.storage_db_path, "prompt", payload["prompt"])
    if "prompt" in payload or "branch_summary_fields" in payload:
        _sync_excel_profile_prompt(config.storage_db_path, payload)
    if "cli_tool" in payload:
        automation_updates["cli_tool"] = str(payload["cli_tool"]).strip()
    if "codex_bin" in payload:
        automation_updates["cli_tool"] = str(payload["codex_bin"]).strip()
    if automation_updates:
        set_setting(config.storage_db_path, "automation", {**automation, **automation_updates})
    return {"ok": True, "config": config_payload(load_config())}


def _sync_excel_profile_prompt(db_path: Path, payload: dict[str, Any]) -> None:
    profile = get_setting(db_path, "excel_profile")
    if not isinstance(profile, dict):
        return

    prompt = profile.get("prompt")
    if not isinstance(prompt, dict):
        prompt = {}
    else:
        prompt = dict(prompt)

    payload_prompt = payload.get("prompt")
    if isinstance(payload_prompt, dict):
        prompt.update(payload_prompt)
    if "branch_summary_fields" in payload:
        prompt["branch_summary_fields"] = payload["branch_summary_fields"]

    set_setting(db_path, "excel_profile", {**profile, "prompt": prompt})


def update_filters(filters: list[dict[str, Any]]) -> dict[str, Any]:
    filter_dicts: list[dict[str, Any]] = []
    for rule in filters:
        field = str(rule.get("field") or "").strip()
        if not field:
            continue
        op = str(rule.get("op") or "equals").strip()
        raw_values: list[str] = rule.get("values") or []
        if isinstance(raw_values, str):
            raw_values = [v.strip() for v in raw_values.split(",") if v.strip()]
        single_value = str(rule.get("value") or "").strip()
        d: dict[str, Any] = {"field": field, "op": op}
        if raw_values:
            d["values"] = ",".join(raw_values)
        elif single_value:
            d["value"] = single_value
        filter_dicts.append(d)
    set_setting(load_config().storage_db_path, "filters", filter_dicts)
    return {"ok": True, "config": config_payload(load_config())}


def add_workspace(payload: dict[str, Any]) -> dict[str, Any]:
    name = str(payload.get("name") or "").strip()
    raw_repos = payload.get("repo_paths") or payload.get("target_repo") or ""
    if isinstance(raw_repos, list):
        repo_paths = [r.strip() for r in raw_repos if r and str(r).strip()]
    else:
        repo_paths = [str(raw_repos).strip()] if str(raw_repos).strip() else []
    target_app_path = str(payload.get("target_app_path") or "").strip()
    if not name:
        raise ValueError("工作区名称不能为空")
    if not repo_paths:
        raise ValueError("仓库路径不能为空")
    for rp in repo_paths:
        if not Path(rp).expanduser().is_dir():
            raise ValueError(f"仓库路径不存在: {rp}")

    target_repo = repo_paths[0]
    workspace_id = name.lower().replace(" ", "-").replace("/", "-")
    scope = str(payload.get("scope") or "frontend").strip()
    scope_paths = str(payload.get("scope_paths") or target_app_path).strip()
    verify_commands = str(payload.get("verify_commands") or "").strip()
    prompt_context_paths = str(payload.get("prompt_context_paths") or "").strip()
    max_concurrency = int(payload.get("max_concurrency") or 2)

    config = load_config()
    existing_ids = {ws.id for ws in config.workspaces}
    if workspace_id in existing_ids:
        suffix = 1
        while f"{workspace_id}-{suffix}" in existing_ids:
            suffix += 1
        workspace_id = f"{workspace_id}-{suffix}"

    new_workspace: dict[str, Any] = {
        "id": workspace_id,
        "name": name,
        "target_repo": target_repo,
        "repo_paths": repo_paths,
        "target_app_path": target_app_path or ".",
        "scope_paths": scope_paths,
        "verify_commands": verify_commands,
        "prompt_context_paths": prompt_context_paths,
        "max_concurrency": max_concurrency,
        "scope": scope,
    }

    existing_workspaces = [_workspace_setting(ws) for ws in config.workspaces]
    existing_workspaces.append(new_workspace)
    set_setting(config.storage_db_path, "workspaces", existing_workspaces)
    new_config = load_config()
    return {"ok": True, "workspace_id": workspace_id, "config": config_payload(new_config)}


def remove_workspace(workspace_id: str) -> dict[str, Any]:
    config = load_config()
    if not any(ws.id == workspace_id for ws in config.workspaces):
        raise ValueError(f"工作区不存在: {workspace_id}")

    remaining = []
    for ws in config.workspaces:
        if ws.id == workspace_id:
            continue
        remaining.append(_workspace_setting(ws))
    set_setting(config.storage_db_path, "workspaces", remaining)
    if config.active_workspace == workspace_id:
        set_setting(config.storage_db_path, "active_workspace", remaining[0]["id"] if remaining else "")
    new_config = load_config()
    return {"ok": True, "config": config_payload(new_config)}


def _workspace_setting(workspace: WorkspaceConfig) -> dict[str, Any]:
    return {
        "id": workspace.id,
        "name": workspace.name,
        "target_repo": str(workspace.target_repo),
        "repo_paths": [str(p) for p in workspace.repo_paths],
        "target_app_path": workspace.target_app_path,
        "scope_paths": ",".join(workspace.scope_paths),
        "verify_commands": ",".join(" ".join(cmd) for cmd in workspace.verify_commands),
        "prompt_context_paths": ",".join(workspace.prompt_context_paths),
        "max_concurrency": workspace.max_concurrency,
        "scope": workspace.scope,
    }
