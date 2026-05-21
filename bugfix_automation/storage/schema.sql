PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS config_snapshots (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  config_json TEXT NOT NULL,
  config_hash TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_settings (
  key TEXT PRIMARY KEY,
  value_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS excel_import_batches (
  id TEXT PRIMARY KEY,
  original_filename TEXT NOT NULL,
  stored_path TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  sheet_name TEXT NOT NULL,
  row_count INTEGER NOT NULL,
  status TEXT NOT NULL,
  config_snapshot_id TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY(config_snapshot_id) REFERENCES config_snapshots(id)
);

CREATE TABLE IF NOT EXISTS excel_import_rows (
  id TEXT PRIMARY KEY,
  batch_id TEXT NOT NULL,
  excel_row INTEGER NOT NULL,
  issue_id TEXT NOT NULL,
  row_json TEXT NOT NULL,
  description TEXT NOT NULL,
  assignee TEXT NOT NULL,
  requester_status TEXT NOT NULL,
  assignee_status TEXT NOT NULL,
  row_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(batch_id) REFERENCES excel_import_batches(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_excel_import_rows_batch_row
  ON excel_import_rows(batch_id, excel_row);

CREATE INDEX IF NOT EXISTS idx_excel_import_rows_issue
  ON excel_import_rows(issue_id);

CREATE TABLE IF NOT EXISTS operations (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  status TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  branch TEXT NOT NULL DEFAULT '',
  issue_id TEXT NOT NULL DEFAULT '',
  excel_row INTEGER,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  config_snapshot_id TEXT,
  excel_import_batch_id TEXT,
  summary TEXT NOT NULL DEFAULT '',
  FOREIGN KEY(config_snapshot_id) REFERENCES config_snapshots(id),
  FOREIGN KEY(excel_import_batch_id) REFERENCES excel_import_batches(id)
);

CREATE INDEX IF NOT EXISTS idx_operations_started
  ON operations(started_at DESC);

CREATE INDEX IF NOT EXISTS idx_operations_branch
  ON operations(branch);

CREATE TABLE IF NOT EXISTS operation_events (
  id TEXT PRIMARY KEY,
  operation_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT '',
  message TEXT NOT NULL DEFAULT '',
  payload_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  FOREIGN KEY(operation_id) REFERENCES operations(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_operation_events_operation_time
  ON operation_events(operation_id, created_at);

CREATE TABLE IF NOT EXISTS artifacts (
  id TEXT PRIMARY KEY,
  operation_id TEXT,
  artifact_type TEXT NOT NULL,
  path TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  mime_type TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  FOREIGN KEY(operation_id) REFERENCES operations(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_artifacts_operation
  ON artifacts(operation_id);

CREATE TABLE IF NOT EXISTS ai_sessions (
  id TEXT PRIMARY KEY,
  operation_id TEXT NOT NULL,
  provider TEXT NOT NULL,
  cli_tool TEXT NOT NULL,
  workspace_path TEXT NOT NULL,
  prompt_path TEXT NOT NULL,
  log_path TEXT NOT NULL,
  status TEXT NOT NULL,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  prompt_sha256 TEXT NOT NULL DEFAULT '',
  log_sha256 TEXT NOT NULL DEFAULT '',
  log_size_bytes INTEGER NOT NULL DEFAULT 0,
  summary_json TEXT NOT NULL DEFAULT '{}',
  FOREIGN KEY(operation_id) REFERENCES operations(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_ai_sessions_operation
  ON ai_sessions(operation_id);

CREATE TABLE IF NOT EXISTS ai_log_segments (
  id TEXT PRIMARY KEY,
  ai_session_id TEXT NOT NULL,
  seq INTEGER NOT NULL,
  offset_start INTEGER NOT NULL,
  offset_end INTEGER NOT NULL,
  line_start INTEGER NOT NULL,
  line_end INTEGER NOT NULL,
  preview TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  FOREIGN KEY(ai_session_id) REFERENCES ai_sessions(id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_log_segments_session_seq
  ON ai_log_segments(ai_session_id, seq);
