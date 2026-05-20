export type IntegrationItem = {
  branch: string;
  source_commit: string;
  apply_method: string;
  status: string;
  changed_files: string[];
  error: string;
};

export type VerifyCommand = {
  command: string;
  status: string;
  log_path: string;
};

export type IntegrationRun = {
  run_id: string;
  workspace_id: string;
  target_branch: string;
  integration_branch: string;
  integration_worktree: string;
  status: string;
  items: IntegrationItem[];
  verify: {
    status: string;
    commands: VerifyCommand[];
  };
  ai_review: {
    status: string;
    summary: string;
  };
  final_commit: string;
  cleaned_branches?: string[];
  created_at: string;
  updated_at: string;
};

export type AvailableBranch = {
  branch: string;
  path: string;
  has_worktree: boolean;
  source_commit: string;
};

export type TargetBranches = {
  current: string;
  branches: string[];
  workspace_id: string;
};
