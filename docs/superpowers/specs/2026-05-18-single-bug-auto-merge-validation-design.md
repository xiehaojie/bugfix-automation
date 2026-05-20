# 单 Bug 自动合并验证设计

## 背景

原有本地 PR 合并队列设计偏向批量集成：用户选择多个 `fix/*` 分支，系统创建集成单，统一预演、统一确认提交。这能覆盖批量场景，但对日常审批台来说概念偏多，容易和旧的“通过并提交”按钮混淆。

新的主流程收缩为单个 bug 修复：AI CLI 自动合并一个 `fix/*` 分支、检查冲突、运行测试并复核 bug 是否解决。用户默认只看到“自动合并验证 → 提交或不提交 → 可撤回”的简单流程。

## 目标

- 每次围绕一个 `fix/*` 分支执行自动合并验证。
- 默认不提交，只生成已合并、已测试、可人工确认的临时结果。
- 用户可以选择提交位置：临时集成分支或目标分支。
- 每个 bug 生成独立 commit，方便撤回单条修复。
- 已提交修复可通过 `git revert` 安全撤回。
- 未提交的预演结果可移除，不影响原始 `fix/*` 分支。
- 页面保持简单，不要求用户理解复杂批量集成队列。

## 非目标

- 第一版不自动 push 到远端。
- 第一版不做复杂批量编排。
- 第一版不自动删除来源分支，清理仍由用户明确触发。
- 第一版不使用 `reset` 或改写历史来撤回提交。

## 推荐流程

```text
选择 fix/* 分支
  ↓
自动合并验证
  ↓
可提交 / 有冲突 / 测试失败 / AI 建议复查
  ↓
用户选择提交或移除预演
  ↓
已提交后可撤回单条提交
```

### 自动合并验证

用户点击“自动合并验证”后，后端执行：

1. 创建或重建单 bug 临时分支：`integration/<safe-bug-branch>-<timestamp>`。
2. 创建对应 integration worktree。
3. 从配置的目标分支拉出临时分支。
4. 应用当前 `fix/*` 分支改动：
   - 有来源 commit：使用 `git cherry-pick -n <commit>`。
   - 只有未提交 diff：使用 `git diff --binary -- <target_app_path>` 和 `git apply --3way`。
5. 记录冲突、失败原因、来源 commit 或 diff 指纹。
6. 运行 workspace 的 `verify_commands`。
7. 调用 AI CLI 阅读 bug 描述、diff 和测试日志，输出复核结论。
8. 保存单 bug 验证记录。

自动合并验证不会生成 commit。

### 提交此修复

只允许在验证结果为 `ready-to-commit` 时提交。

提交位置由用户选择：

- `integration`：提交到临时集成分支，目标分支不变。
- `target`：把验证后的 diff 应用到目标分支，并在目标分支生成单 bug commit。

提交信息示例：

```text
fix(pc-web): apply AI fix for bug 29

Source branch: fix/bug-29-文件解析识别图片方面的效果不太好待期
Verification: passed
AI review: suggest-pass
```

提交后记录：

- `final_commit`
- `final_commit_location`
- `target_branch`
- `integration_branch`
- `source_branch`
- `source_commit` 或 `diff_fingerprint`
- `verify_status`
- `ai_review_status`

### 撤回此提交

只允许在 `committed` 状态撤回。

撤回规则：

- 如果 `final_commit_location = integration`，在 integration worktree 中执行 `git revert <final_commit>`。
- 如果 `final_commit_location = target`，在目标分支中执行 `git revert <final_commit>`。
- 成功后记录 `revert_commit` 和 `reverted_at`。
- 状态变为 `reverted`。

撤回必须生成反向提交，不允许 `reset`。

### 移除此预演

适用于尚未提交的状态：

- `ready-to-commit`
- `conflict`
- `verify-failed`
- `ai-review-needed`

移除操作只删除 integration worktree 和临时 integration 分支，不删除原始 `fix/*` 分支。状态回到 `pending`。

### 清理来源分支

只允许用户显式点击。

建议只在 `committed` 状态允许清理，不在 `reverted` 状态自动清理，避免用户撤回后还想继续修改原分支。

清理内容：

- 对应 `fix/*` 本地分支。
- 对应 `.target-worktrees/*` worktree。

清理前必须确认：

- 来源分支仍是本地 `fix/*` 分支。
- 验证记录中已有 `final_commit`。
- 当前状态不是冲突或验证失败。

## 状态模型

```text
pending
  ↓ 自动合并验证
verifying
  ↓ 成功
ready-to-commit
  ↓ 提交此修复
committed
  ↓ 撤回此提交
reverted
```

失败路径：

```text
verifying
  ├─ conflict
  ├─ verify-failed
  └─ ai-review-needed
```

清理路径：

```text
committed
  ↓ 清理来源分支
cleaned
```

移除预演路径：

```text
ready-to-commit / conflict / verify-failed / ai-review-needed
  ↓ 移除此预演
pending
```

## 页面设计

第一版不再把“集成预演”作为复杂独立流程，而是融入现有审批台的单分支详情区。

### 左侧列表

每个分支显示当前状态：

- 待验证
- 验证中
- 可提交
- 有冲突
- 测试失败
- AI 建议复查
- 已提交
- 已撤回
- 已清理

### 中间主区域

顶部显示单 bug 合并验证卡片。

待验证：

```text
状态：待合并验证

[自动合并验证] [重新修复] [拒绝] [清理]
```

验证中：

```text
合并验证中...

1. 创建临时集成分支      ✓
2. 应用修复改动          ✓
3. 检查冲突              ✓
4. 运行测试              进行中
5. AI 复核               等待中
```

可提交：

```text
状态：可提交

合并分支：integration/bug-29-20260519-1111
测试结果：通过
AI 复核：建议通过
累计改动：5 个文件

提交位置：
(●) 临时集成分支：更安全，目标分支不变
( ) 目标分支 main：更直接，可通过撤回生成反向提交

[提交此修复] [移除此预演] [重新验证]
```

失败：

```text
状态：有冲突 / 测试失败 / AI 建议复查

冲突文件或失败日志：
- apps/pc-web/src/...

[重新修复] [移除此预演] [查看日志]
```

已提交到 integration：

```text
状态：已提交到临时集成分支
提交：abc1234
说明：目标分支 main 尚未改变

[撤回此提交] [打开集成 worktree] [清理来源分支]
```

已提交到目标分支：

```text
状态：已提交到目标分支 main
提交：abc1234
说明：此修复已经进入目标分支，可通过撤回生成反向提交

[撤回此提交] [清理来源分支]
```

### 右侧 AI 区域

保留现有 AI 对话/复核区域，用于：

- 展示 AI 复核结论。
- 展示测试日志摘要。
- 触发继续 rework。

## 后端 API

建议新增或收敛为单 bug 语义接口：

```text
GET  /api/fix-validations/{branch}
POST /api/fix-validations/{branch}/verify
POST /api/fix-validations/{branch}/commit
POST /api/fix-validations/{branch}/revert
POST /api/fix-validations/{branch}/remove-preview
POST /api/fix-validations/{branch}/cleanup-source
```

`POST /api/fix-validations/{branch}/commit` 请求体：

```json
{
  "location": "integration"
}
```

或：

```json
{
  "location": "target"
}
```

## 数据模型

单 bug 验证记录保存到：

```text
runs/fix-validations/<safe-branch>/validation.json
```

建议结构：

```json
{
  "branch": "fix/bug-29-文件解析识别图片方面的效果不太好待期",
  "target_branch": "main",
  "integration_branch": "integration/bug-29-20260519-1111",
  "integration_worktree": ".integration-worktrees/bug-29-20260519-1111",
  "status": "ready-to-commit",
  "apply_method": "cherry-pick-no-commit",
  "source_commit": "abc1234",
  "diff_fingerprint": "",
  "changed_files": ["apps/pc-web/src/app/example.tsx"],
  "verify": {
    "status": "passed",
    "commands": [
      {
        "command": "npm run build",
        "status": "passed",
        "log_path": "runs/fix-validations/bug-29/build.log"
      }
    ]
  },
  "ai_review": {
    "status": "suggest-pass",
    "summary": "改动覆盖了问题描述，未发现明显回归风险。"
  },
  "final_commit": "",
  "final_commit_location": "",
  "revert_commit": "",
  "created_at": "2026-05-19T11:11:00+08:00",
  "updated_at": "2026-05-19T11:20:00+08:00"
}
```

## 安全限制

提交到目标分支时必须满足：

1. 目标 repo 当前工作区 clean。
2. 只能应用 `target_app_path` 范围内 diff。
3. 提交前重新从验证结果生成 diff 并 apply，不复用旧假设。
4. 不自动 push。
5. 撤回只用 `git revert`。
6. 不删除非 `fix/*` 分支。

## 与旧流程的关系

旧的“通过并提交”按钮应被替换或降级：

- 主按钮改为“自动合并验证”。
- 旧的直接提交能力不作为默认入口展示。
- 如果保留，应改名为“单分支直接提交”，并加二次确认。

原来的批量集成单能力可以暂时隐藏。后续如果需要批量处理，可以把多个单 bug 验证任务串起来，而不是让用户直接面对复杂批量集成概念。

## 测试策略

后端测试：

- 能为单个 `fix/*` 创建 integration worktree。
- 能应用有 commit 的分支。
- 能应用未提交 diff。
- 冲突时标记 `conflict` 并保留来源分支。
- 验证命令失败时标记 `verify-failed`。
- AI 复核失败时标记 `ai-review-needed`，但不破坏 Git 结果。
- 可提交状态能提交到 integration 分支。
- 可提交状态能提交到目标分支，并要求目标工作区 clean。
- committed 状态能通过 `git revert` 撤回。
- remove-preview 只删除 integration worktree 和 integration 分支。
- cleanup-source 只删除已提交的 `fix/*` 来源分支。

前端测试：

- 不同状态展示正确主按钮。
- 验证中展示流水线进度。
- 可提交状态展示提交位置选择。
- 失败状态展示冲突文件或验证日志。
- 已提交到 integration 和已提交到 target 的文案不同。
- 撤回按钮只在 committed 状态出现。

## MVP 实施顺序

1. 后端单 bug 验证服务：verify、commit、revert、remove-preview。
2. API 路由：提供单分支验证记录和操作接口。
3. 审批台 UI：替换“通过并提交”为“自动合并验证”状态卡片。
4. 提交位置选择：先支持 integration，再支持 target。
5. 撤回：对 integration 和 target 都使用 `git revert`。
6. 清理来源分支：保留为显式操作。
