# 轻量级数据存储方案

> **给执行代理:** 如果后续要按本文落地实现，建议使用 `superpowers:subagent-driven-development` 或 `superpowers:executing-plans`，按任务逐项实现和验证。

**目标:** 为当前 bugfix 自动化工具补一层轻量级本地存储，覆盖配置信息、用户导入 Excel 记录、用户执行操作记录、操作历史记录，以及很长的 AI 执行记录。

**总体架构:** 使用 **SQLite 存元数据和索引，文件系统存大对象**。当前 `config.yaml` 继续作为人工可编辑的当前配置来源；SQLite 负责保存执行时的配置快照、Excel 导入批次、操作流水和 AI 日志索引。AI 完整日志不直接塞进数据库，而是写入日志文件，再通过偏移量分页读取。

**技术栈:** Python 标准库 `sqlite3`、`json`、`hashlib`、`pathlib`，沿用当前 FastAPI 后端、pytest 测试和已有目录结构。

---

## 一、推荐目录结构

```text
data/
  app.sqlite3
  app.sqlite3-shm
  app.sqlite3-wal

uploads/
  用户上传的 Excel 原文件

runs/
  artifacts/
    excel-imports/<import_id>/row-images/...
    operations/<operation_id>/...

logs/
  ai/
    <ai_session_id>/
      full.log
      prompt.txt
      summary.json
```

建议新增两个配置项：

```yaml
data_root: data
storage_db_path: data/app.sqlite3
```

环境变量覆盖：

```bash
BUGFIX_DATA_ROOT=/path/to/data
BUGFIX_STORAGE_DB_PATH=/path/to/app.sqlite3
```

## 二、存储分工

SQLite 只存“小而可查”的数据：

- 配置快照。
- Excel 导入批次。
- Excel 每行的结构化快照。
- 用户触发的操作记录。
- 后端状态流转事件。
- AI 会话元数据。
- AI 日志文件路径、大小、hash、分段索引、摘要。

文件系统存“大而长”的数据：

- Excel 原文件。
- Excel 中导出的截图。
- AI prompt 全文。
- AI 执行完整日志。
- diff、报告、附件等可复现材料。

这样设计的好处：

- SQLite 文件小，查询快，备份简单。
- AI 日志再长也不会撑爆数据库。
- 前端接口可以分页、tail、按 offset 读日志。
- 后面如果要换 PostgreSQL，也比较容易迁移。

## 三、核心数据表

### 1. `config_snapshots`

记录每次关键操作开始时的配置快照。

用途：

- 追溯某次执行到底用了什么配置。
- 防止后来 `config.yaml` 改了之后，历史记录失真。

字段建议：

```sql
CREATE TABLE IF NOT EXISTS config_snapshots (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  config_json TEXT NOT NULL,
  config_hash TEXT NOT NULL,
  created_at TEXT NOT NULL
);
```

说明：

- `source`: `run_once`、`run_one`、`excel_upload`、`integration` 等。
- `config_json`: 当时配置的 JSON 快照。
- `config_hash`: 用于判断配置是否发生变化。

### 2. `excel_import_batches`

记录用户每次导入 Excel 的批次。

```sql
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
```

说明：

- `stored_path`: 实际保存到 `uploads/` 下的路径。
- `sha256`: 判断是否重复上传或文件是否被改动。
- `row_count`: 导入行数。
- `status`: `imported`、`failed`、`archived`。

### 3. `excel_import_rows`

记录 Excel 每一行的结构化快照。

```sql
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
```

说明：

- `row_json`: 保留完整行数据，方便以后字段增加。
- 常用字段单独冗余出来，方便列表查询和筛选。
- `row_hash`: 判断同一条问题内容是否变化。

### 4. `operations`

记录用户或系统触发的一次顶层操作。

```sql
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
```

`kind` 建议枚举：

- `excel_upload`
- `run_once`
- `run_one`
- `approval_accept`
- `approval_reject`
- `rework`
- `integration_create`
- `integration_start`
- `integration_commit`

`status` 建议枚举：

- `queued`
- `running`
- `succeeded`
- `failed`
- `cancelled`
- `blocked`

### 5. `operation_events`

记录一次操作内部发生的流水事件，采用 append-only 方式。

```sql
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
```

适合记录：

- 用户点击了“立即执行一次”。
- 某条 bug 进入 queued。
- AI 开始执行。
- AI 执行结束。
- 验证开始。
- 验证失败。
- 用户审批通过或驳回。
- 集成分支创建、冲突、验证失败、提交成功。

### 6. `artifacts`

统一记录文件型产物。

```sql
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
```

`artifact_type` 示例：

- `excel`
- `image`
- `prompt`
- `ai_log`
- `diff`
- `report`
- `summary`

### 7. `ai_sessions`

记录一次 AI 执行会话。

```sql
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
```

说明：

- `prompt_path`: prompt 全文路径。
- `log_path`: AI 完整日志路径。
- `summary_json`: AI 执行摘要，比如修改文件数、最终状态、失败原因摘要。

### 8. `ai_log_segments`

记录 AI 长日志的分段索引。

```sql
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
```

建议每 64 KiB 建一个 segment：

- 前端默认只取最后 120000 字符。
- 用户滚动时按 `offset` 和 `limit` 继续加载。
- 搜索时可以先扫 `preview`，必要时再读文件。

## 四、AI 长日志处理方案

AI 执行记录会非常长，不建议这样做：

- 不要把完整日志存进 SQLite 的一个 TEXT 字段。
- 不要每次接口请求都 `read_text()` 读完整文件。
- 不要让前端一次性渲染几 MB 甚至几十 MB 日志。

推荐流程：

1. 创建 AI 会话：

```text
logs/ai/<ai_session_id>/prompt.txt
logs/ai/<ai_session_id>/full.log
logs/ai/<ai_session_id>/summary.json
```

2. 执行 AI 时，把 stdout/stderr 持续追加到 `full.log`。

3. 执行结束后计算：

```text
log_size_bytes
log_sha256
summary_json
```

4. 对 `full.log` 建分段索引：

```text
segment_size = 65536 bytes
seq = 1, 2, 3...
offset_start / offset_end
line_start / line_end
preview
```

5. 日志接口支持：

```http
GET /api/logs?branch=fix/demo
GET /api/logs?branch=fix/demo&offset=0&limit=120000
GET /api/ai-sessions/<id>/logs?offset=65536&limit=65536
GET /api/ai-sessions/<id>/logs/tail?limit=120000
```

返回结构：

```json
{
  "path": "logs/ai/ai_xxx/full.log",
  "offset": 65536,
  "next_offset": 131072,
  "size": 2097152,
  "content": "..."
}
```

这样可以保证：

- 前端日志面板稳定。
- 后端内存占用可控。
- 日志文件再大也能逐段读取。
- 历史 AI 记录可追溯。

## 五、写入时机设计

### 上传 Excel

流程：

1. 保存原始文件到 `uploads/`。
2. 校验 `.xlsx`。
3. 计算 sha256。
4. 读取 Excel 行。
5. 写入 `excel_import_batches`。
6. 写入 `excel_import_rows`。
7. 更新 `config.yaml` 中的 `excel_path`。
8. 写一条 `operations(kind='excel_upload')`。
9. 写一条 `operation_events(event_type='excel_imported')`。

### 执行 `run_once`

流程：

1. 创建 `config_snapshots`。
2. 创建 `operations(kind='run_once')`。
3. 读取当前 Excel。
4. 对每条命中的 bug 写 `operation_events`。
5. 每条 bug 开始处理时，可以创建子 operation，或继续挂在同一个 operation 下。
6. AI 开始时创建 `ai_sessions`。
7. AI 结束后更新 `ai_sessions`，并写 `ai_log_segments`。
8. 验证结束后更新 `operations.status`。

### 执行 `run_one`

流程：

1. 创建 `config_snapshots`。
2. 创建 `operations(kind='run_one')`，写入 `issue_id` 和 `excel_row`。
3. 创建 worktree。
4. 创建 AI session。
5. 写 AI 日志文件。
6. 写 AI 日志索引。
7. 写验证事件。
8. 最终更新 operation 状态。

### 审批操作

用户点击通过、驳回、重新执行时：

1. 创建 `operations(kind='approval_accept' | 'approval_reject' | 'rework')`。
2. 写 `operation_events`。
3. 记录 branch、issue_id、excel_row、用户备注。
4. 如果产生新 AI 执行，则创建新的 `ai_sessions`。

### 集成操作

当前已有 `runs/integration-runs/<run_id>/integration-run.json`，可以保留兼容。

建议新增：

- `operations(kind='integration_create')`
- `operations(kind='integration_start')`
- `operations(kind='integration_commit')`
- 每个分支 apply 状态写入 `operation_events`

## 六、与当前代码的落地点

建议新增文件：

```text
bugfix_automation/storage/__init__.py
bugfix_automation/storage/schema.sql
bugfix_automation/storage/db.py
bugfix_automation/storage/artifacts.py
bugfix_automation/storage/repositories.py
bugfix_automation/application/history_service.py
bugfix_automation/api/routes/history.py
```

建议修改文件：

```text
bugfix_automation/config.py
bugfix_automation/application/excel_service.py
bugfix_automation/runner.py
bugfix_automation/task_state.py
bugfix_automation/application/log_service.py
bugfix_automation/api/routes/logs.py
bugfix_automation/api/app.py
```

测试文件：

```text
tests/test_storage.py
tests/test_excel_storage.py
tests/test_ai_log_storage.py
tests/test_fastapi_api.py
```

## 七、推荐 API

### 操作历史

```http
GET /api/history/operations?limit=100
GET /api/history/operations/<operation_id>
GET /api/history/operations/<operation_id>/events
```

### Excel 导入记录

```http
GET /api/history/excel-imports?limit=50
GET /api/history/excel-imports/<batch_id>
GET /api/history/excel-imports/<batch_id>/rows?limit=200&offset=0
```

### AI 会话

```http
GET /api/history/ai-sessions?operation_id=<operation_id>
GET /api/history/ai-sessions/<ai_session_id>
GET /api/history/ai-sessions/<ai_session_id>/logs?offset=0&limit=65536
GET /api/history/ai-sessions/<ai_session_id>/logs/tail?limit=120000
```

## 八、保留策略

轻量级方案不需要一开始做复杂归档，可以先这样：

- SQLite 永久保留。
- Excel 原文件永久保留，或手动清理。
- AI 完整日志默认保留 30 天。
- AI 摘要、日志 hash、日志大小、最终状态永久保留。
- `runs/` 下报告继续保留。

后续可以加一个命令：

```bash
python3 -m bugfix_automation.cli prune-history --days 30
```

清理内容：

- 删除 30 天前的 `logs/ai/*/full.log`。
- 保留 `summary.json`。
- 保留 SQLite 中的 `ai_sessions` 和 `operation_events`。
- 将对应 artifact 标记为 archived 或 missing。

## 九、落地顺序

### 第 1 步：加配置项

目标：

- 在 `Config` 中增加 `data_root` 和 `storage_db_path`。
- 默认路径为 `data/app.sqlite3`。
- 支持环境变量覆盖。

验证：

```bash
python3 -m pytest tests/test_config.py -v
```

### 第 2 步：加 SQLite schema

目标：

- 新增 `storage/schema.sql`。
- 新增 `storage/db.py`。
- 实现 `ensure_schema(db_path)`。
- 开启 WAL 和 foreign keys。

验证：

```bash
python3 -m pytest tests/test_storage.py -v
```

### 第 3 步：加 repository 层

目标：

- `save_config_snapshot`
- `save_excel_import`
- `create_operation`
- `append_operation_event`
- `finish_operation`
- `create_ai_session`
- `finish_ai_session`
- `index_ai_log_segments`
- `read_ai_log_slice`

验证：

```bash
python3 -m pytest tests/test_storage.py tests/test_ai_log_storage.py -v
```

### 第 4 步：接入 Excel 上传

目标：

- 上传 Excel 后写入导入批次。
- 解析每行并保存行快照。
- 记录上传操作事件。

验证：

```bash
python3 -m pytest tests/test_excel_storage.py tests/test_excel_reader.py tests/test_fastapi_api.py -v
```

### 第 5 步：接入任务执行历史

目标：

- `run_once` 和 `run_one` 创建 operation。
- `set_task_state` 同步追加 operation event。
- 审批和集成动作逐步补操作事件。

验证：

```bash
python3 -m pytest tests/test_approval.py tests/test_scheduler.py tests/test_integration_service.py -v
```

### 第 6 步：改造日志读取

目标：

- AI 完整日志继续写文件。
- 日志读取接口支持 `offset` 和 `limit`。
- 默认读取尾部 120000 字符，兼容当前前端。

验证：

```bash
python3 -m pytest tests/test_ai_log_storage.py tests/test_fastapi_api.py -v
```

### 第 7 步：加历史查询 API

目标：

- `/api/history/operations`
- `/api/history/operations/{id}/events`
- `/api/history/excel-imports`
- `/api/history/ai-sessions/{id}/logs`

验证：

```bash
python3 -m pytest tests/test_fastapi_api.py -v
```

## 十、最终建议

这个项目目前还是本地自动化工具，不建议一开始上 PostgreSQL、ORM 或复杂事件系统。

最合适的版本是：

```text
SQLite = 索引、状态、历史、快照
文件系统 = Excel、图片、prompt、完整 AI 日志、报告
JSON = 少量兼容旧逻辑的状态文件
```

AI 长日志一定要按文件存，并且接口分页读取。数据库只负责回答这些问题：

- 这次 AI 执行是谁触发的？
- 对应哪条 Excel 记录？
- 用了哪份配置？
- 日志文件在哪？
- 日志有多大？
- 最终结果是什么？
- 有哪些关键事件？

这样既轻量，又能满足后续审计、回放、搜索和前端历史页展示。
