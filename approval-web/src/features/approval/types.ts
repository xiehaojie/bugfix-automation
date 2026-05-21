export type FixItem = {
  branch: string;
  path: string;
  changed_files: string[];
  pending: boolean;
  active: boolean;
  task_status: string;
  task_phase: string;
  task_detail: string;
  task_updated_at: string;
  status: string;
  diff: string;
  log_path?: string;
  excel_row?: number;
  issue_id?: string;
  description?: string;
};

export type DashboardPayload = {
  pending_count: number;
  items: FixItem[];
};

export type BugItem = {
  issue_id: string;
  excel_row: number;
  branch: string;
  source_system: string;
  primary_category: string;
  secondary_category: string;
  requester_status: string;
  assignee_status: string;
  description: string;
  remark: string;
  remark2: string;
  active: boolean;
  task_status: string;
  task_phase: string;
  task_detail: string;
  task_updated_at: string;
  images: Array<{ path: string; name: string; url: string }>;
};

export type Workspace = {
  id: string;
  name: string;
  target_repo: string;
  repo_paths: string[];
  target_app_path: string;
  scope_paths: string[];
  verify_commands: string[];
  prompt_context_paths: string[];
  max_concurrency: number;
  scope: string;
};

export type FilterRule = {
  field: string;
  op: string;
  value: string;
  values: string[];
};

export type ConfigPayload = {
  target_repo: string;
  target_app_path: string;
  excel_path: string;
  excel_file: {
    path?: string;
    original_name?: string;
    stored_name?: string;
    size?: number;
    mtime?: string;
    sha256?: string;
  };
  assignee: string;
  api_port: number;
  active_workspace: string;
  max_concurrency: number;
  cli_tool: string;
  workspaces: Workspace[];
  filters: FilterRule[];
  branch_summary_fields: string[];
  prompt: {
    fields: string[];
    template: string;
    context_paths: string[];
  };
};

export type SchedulerPayload = {
  label: string;
  plist_path: string;
  installed: boolean;
  loaded: boolean;
  schedule_hour: number;
  schedule_minute: number;
};

export type LogPayload = {
  branch: string;
  path: string;
  content: string;
  offset?: number;
  next_offset?: number;
  size?: number;
};

export type TaskLike = {
  active: boolean;
  pending?: boolean;
  task_status: string;
  task_phase: string;
  task_detail: string;
};

export type FixValidationStatus =
  | "pending"
  | "verifying"
  | "ready-to-commit"
  | "committed"
  | "reverted"
  | "conflict"
  | "verify-failed"
  | "ai-review-needed"
  | "preview-removed"
  | "cleaned";

export type CommitLocation = "integration" | "target";

export type FixValidationCommand = {
  command: string;
  status: string;
  log_path: string;
  log_tail?: string;
};

export type FixValidation = {
  branch: string;
  run_id: string;
  target_branch: string;
  integration_branch: string;
  integration_worktree: string;
  status: FixValidationStatus;
  apply_method: string;
  source_commit: string;
  changed_files: string[];
  verify: {
    status: string;
    commands: FixValidationCommand[];
  };
  ai_review: {
    status: string;
    summary: string;
  };
  final_commit: string;
  final_commit_location: CommitLocation | "";
  revert_commit: string;
  error: string;
  created_at: string;
  updated_at: string;
};

export type HistoryStats = {
  total: number;
  runs: number;
  submitted: number;
  rejected: number;
  reworked: number;
  previewed: number;
  failed: number;
};

export type HistoryOperation = {
  id: string;
  kind: string;
  status: string;
  workspace_id: string;
  branch: string;
  original_branch?: string;
  issue_id: string;
  excel_row?: number | null;
  started_at: string;
  ended_at?: string | null;
  summary: string;
  summary_text: string;
  summary_data: Record<string, unknown>;
};

export type HistoryEvent = {
  id: string;
  operation_id: string;
  event_type: string;
  status: string;
  message: string;
  payload_json: string;
  created_at: string;
};

export type HistoryAiSession = {
  id: string;
  operation_id: string;
  provider: string;
  cli_tool: string;
  workspace_path: string;
  prompt_path: string;
  log_path: string;
  status: string;
  started_at: string;
  ended_at?: string | null;
  prompt_preview: string;
  log_preview: string;
  summary_data: Record<string, unknown>;
};

export type HistoryOperationsPayload = {
  items: HistoryOperation[];
  stats: HistoryStats;
};

export type HistoryDetailPayload = {
  operation: HistoryOperation;
  events: HistoryEvent[];
  related_operations?: HistoryOperation[];
  ai_sessions: HistoryAiSession[];
  diff_preview: string;
  changed_files: string[];
};
