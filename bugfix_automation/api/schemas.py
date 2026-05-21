from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class BranchRequest(BaseModel):
    branch: str = ""


class BugRowRequest(BaseModel):
    excel_row: int = 0


class OptimizePromptRequest(BaseModel):
    prompt: str = ""
    excel_row: int = 0


class ConfigUpdateRequest(BaseModel):
    max_concurrency: int | None = None
    branch_summary_fields: list[str] | None = None
    prompt: dict[str, Any] | None = None


class FilterRuleItem(BaseModel):
    field: str
    op: str
    value: str = ""
    values: list[str] = []


class FiltersUpdateRequest(BaseModel):
    filters: list[FilterRuleItem] = []


class ExcelPathRequest(BaseModel):
    path: str = ""


class ReworkRequest(BaseModel):
    branch: str = ""
    note: str = ""
    file_paths: list[str] = []
    image_paths: list[str] = []
    cli_tool: str = ""


class ScheduleInstallRequest(BaseModel):
    hour: int
    minute: int


class WorkspaceSelectRequest(BaseModel):
    workspace_id: str = ""


class WorkspaceAddRequest(BaseModel):
    name: str = ""
    repo_paths: list[str] = []
    target_app_path: str = ""
    scope: str = "frontend"
    scope_paths: str = ""
    verify_commands: str = ""
    prompt_context_paths: str = ""


class IntegrationCreateRequest(BaseModel):
    workspace_id: str = ""
    target_branch: str = ""
    branches: list[str] = []
    target_repo: str = ""
    repo_paths: list[str] = []
    target_app_path: str = ""
    scope: str = "frontend"
    scope_paths: str = ""
    verify_commands: str = ""
    prompt_context_paths: str = ""
    max_concurrency: int = 2


class FixValidationCommitRequest(BaseModel):
    location: str = "integration"


class WorkspaceRemoveRequest(BaseModel):
    workspace_id: str = ""
