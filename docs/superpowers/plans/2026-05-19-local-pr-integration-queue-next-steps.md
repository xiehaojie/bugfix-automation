# 本地 PR 合并队列后续步骤

## 目标

把“AI 修复完成后，自动集成、验证、记录、等待人工确认提交”的流程分阶段落地。Git 写操作由确定性脚本执行，本机各种 AI-cli 工具负责复核、解释、归因、生成验证建议和提交说明。

关联设计文档：

- `docs/superpowers/specs/2026-05-19-local-pr-integration-queue-design.md`

## 总体原则

- AI-cli 可以读代码、读 diff、跑验证、解释日志、生成建议。
- AI-cli 不直接拥有最终提交、删除分支、标记 Excel 已处理的权限。
- 合并、提交、清理分支等不可逆动作必须由后端服务执行，并保留集成单记录。
- 用户确认前，所有改动只进入 integration worktree，不污染用户正在工作的目标分支。
- 冲突、验证失败、AI 复核不通过的来源分支默认保留。

## 阶段 1：确定性集成底座

先做不依赖 AI 的核心流程，保证 Git 行为稳定可回滚。

### 后端能力

- 新增 integration service。
- 创建 `runs/integration-runs/<run_id>/integration-run.json`。
- 创建 `.integration-worktrees/<run_id>`。
- 从目标分支拉出 `integration/*` 临时分支。
- 按顺序应用多个 `fix/*` 分支。
- 自动判断应用方式：
  - 有提交：`git cherry-pick -n <commit>`。
  - 未提交 worktree：提取 diff 后 `git apply --3way`。
- 记录每个来源分支的应用状态、来源 commit 或 diff 指纹、改动文件和错误信息。
- 跑当前工作区配置的 `verify_commands`。
- 生成 Markdown 报告。

### CLI 能力

新增命令：

```bash
python3 -m bugfix_automation.cli integration-create
python3 -m bugfix_automation.cli integration-start --run-id <run_id>
python3 -m bugfix_automation.cli integration-confirm --run-id <run_id>
python3 -m bugfix_automation.cli integration-cleanup --run-id <run_id>
```

第一版也可以合并为一个命令：

```bash
python3 -m bugfix_automation.cli integrate \
  --target main \
  --branches fix/1-xxx fix/2-xxx
```

### 验收标准

- 可以在测试仓库里成功创建 integration worktree。
- 可以把多个 `fix/*` 分支叠加到 integration 分支且不自动提交。
- 验证失败时保留现场并写入状态。
- 冲突时停止后续应用，不删除任何来源分支。

## 阶段 2：审批台集成预演页面

在页面里把集成单看清楚，让用户不需要翻终端日志。

### 页面能力

- 新增“集成预演”入口。
- 展示集成单列表。
- 展示单个集成单详情：
  - 目标分支。
  - 集成分支。
  - 集成 worktree。
  - 来源分支列表。
  - 每个分支的应用状态。
  - 冲突或失败原因。
  - 验证命令结果。
  - 最终累计 diff。
- 支持创建集成单。
- 支持开始集成。
- 支持确认提交。
- 支持清理已合入来源分支。
- 对 `blocked`、`verify-failed` 状态给明确提示，不展示成可安全清理。

### API 能力

新增接口：

```text
GET  /api/integration-runs
GET  /api/integration-runs/{run_id}
POST /api/integration-runs
POST /api/integration-runs/{run_id}/start
POST /api/integration-runs/{run_id}/confirm
POST /api/integration-runs/{run_id}/cleanup
POST /api/integration-runs/{run_id}/abort
```

### 验收标准

- 用户能从页面选择目标分支和待集成 `fix/*` 分支。
- 用户能看到每个来源分支是否成功应用。
- 用户能在页面完成“确认提交”和“清理来源分支”。
- 页面不会误删失败分支、冲突分支或非 `fix/*` 分支。

## 阶段 3：AI-cli 单分支复核

在每个 `fix/*` 分支修完后，调用本机 AI-cli 做一次轻量验收。

### AI 输入

- bug 原始描述。
- Excel 行信息。
- 截图路径。
- 分支 diff。
- 改动文件列表。
- lint/build/test 日志。

### AI 输出

写入 task state 或 integration item：

```json
{
  "status": "suggest-pass",
  "summary": "改动覆盖了收藏夹 skill 展示问题，未发现明显无关改动。",
  "risk": "低",
  "manual_check_steps": [
    "打开个人空间收藏夹",
    "查看 skill 类型收藏是否正常展示",
    "点击列表项确认跳转正常"
  ]
}
```

状态建议：

- `suggest-pass`: 建议通过。
- `needs-human-review`: 建议人工复查。
- `blocked`: 不建议合入。
- `ai-review-failed`: AI 复核失败，但不阻断人工判断。

### 验收标准

- 单分支详情里能展示 AI 复核摘要。
- AI 复核失败不影响 Git 状态。
- AI 输出必须可追溯到日志文件。

## 阶段 4：AI-cli 集成后整体复核

多个分支叠加后，再让 AI 看最终累计 diff，检查组合风险。

### AI 重点检查

- 是否有多个分支修改同一文件或同一逻辑。
- 后应用的分支是否覆盖了先应用分支的修复。
- 是否有重复实现。
- 是否有明显无关改动。
- 是否有公共组件、路由、状态管理、接口封装等高风险改动。
- 验证失败是否能归因到某个来源分支。

### AI 输出

写入 `integration-run.json` 的 `ai_review`：

```json
{
  "status": "needs-human-review",
  "summary": "整体 diff 可以构建，但 fix/37 与 fix/24 都修改了收藏列表渲染逻辑，建议重点人工验证收藏夹列表和待办列表。",
  "risk_items": [
    {
      "branch": "fix/37-xxx",
      "risk": "修改公共列表组件，可能影响收藏夹和待办列表"
    }
  ],
  "manual_check_steps": [
    "验证收藏夹 skill 列表",
    "验证重复待办列表",
    "验证移动端文件类型筛选"
  ]
}
```

### 验收标准

- 集成单详情显示整体 AI 复核结论。
- 用户能直接看到推荐人工验证路径。
- AI 复核结论不会自动触发提交或删除分支。

## 阶段 5：AI-cli 日志解释和失败归因

当验证命令失败时，让 AI 读日志并总结原因。

### AI 输入

- 失败命令。
- 完整日志或尾部日志。
- 当前累计 diff。
- 每个来源分支改动文件。

### AI 输出

```json
{
  "failure_type": "introduced-by-integration",
  "likely_branch": "fix/37-xxx",
  "summary": "TypeScript 类型错误来自待办列表组件新增字段未处理空值。",
  "suggested_action": "回退 fix/37 后重跑，或补充空值判断。"
}
```

失败类型：

- `introduced-by-integration`: 本次集成引入。
- `pre-existing`: 目标分支已有问题。
- `environment`: 本地环境问题。
- `unknown`: 无法判断。

### 验收标准

- 验证失败时页面展示 AI 解释。
- AI 能给出最可能的来源分支。
- 用户能根据建议决定回退、重做或人工处理。

## 阶段 6：AI-cli 生成提交说明和归档报告

用户确认提交前，让 AI 生成最终提交信息和变更报告。

### Commit message

示例：

```text
fix(pc-web): batch apply AI bug fixes

Included fixes:
- fix/24-收藏夹中展示的收藏列表展示的skill
- fix/37-可能会接收到多个重复待办希望能够帮我

Verification:
- npm run lint: passed
- npm run build: passed

Integration run: 20260520-0900-pc-web-main
```

### 归档报告

报告包含：

- 最终 commit。
- 已合入分支。
- 已清理分支。
- 保留分支及原因。
- 验证结果。
- AI 复核摘要。
- 人工验证建议。

### 验收标准

- 用户确认前能预览提交信息。
- 提交后集成单记录 `final_commit`。
- 清理后记录已删除来源分支。

## 阶段 7：浏览器或 E2E 验证增强

这是增强项，不放在第一版阻塞路径上。

### 能力

- 启动目标项目本地服务。
- 根据 bug 描述生成 Playwright 验证步骤。
- 对关键页面执行简单浏览器验证。
- 保存截图、控制台错误和页面状态。
- 将结果写入集成单报告。

### 适合验证的场景

- 列表展示。
- 筛选条件。
- 按钮交互。
- 表单状态。
- 文件预览或上传入口。

### 不适合完全自动验证的场景

- 依赖真实账号权限。
- 依赖线上数据。
- 依赖复杂后端状态。
- 需要人工视觉判断的 UI 细节。

## 阶段 8：AI 辅助冲突处理

这是高风险增强项，必须放在用户确认后再启用。

### 能力

- 解释冲突来自哪些来源分支。
- 总结双方修改意图。
- 生成建议补丁。
- 标记需要人工检查的文件。

### 边界

- AI 不自动继续删除分支。
- AI 不自动最终提交。
- 冲突解决后的集成单必须重新跑验证。
- 页面必须显示“冲突曾发生过”的历史记录。

## 推荐落地顺序

1. 先实现阶段 1，打稳确定性 Git 集成底座。
2. 再实现阶段 2，让审批台能看到集成单。
3. 接入阶段 3，让每个 `fix/*` 分支都有 AI 验收摘要。
4. 接入阶段 4，让集成后的累计 diff 有整体复核。
5. 接入阶段 5，降低验证失败时的排查成本。
6. 接入阶段 6，让提交说明和归档自动生成。
7. 最后再做阶段 7 和阶段 8。

## 最小可用版本

第一版做到这些就有实际价值：

- 页面选择目标分支和多个 `fix/*` 分支。
- 创建 integration worktree。
- 自动应用分支但不提交。
- 跑 `verify_commands`。
- 生成集成单 JSON 和 Markdown 报告。
- 页面展示状态、累计 diff 和验证日志。
- 用户确认后生成最终 commit。
- 成功后删除已合入 `fix/*` 分支和 worktree。

AI-cli 第一版只做三件事：

- 单分支复核摘要。
- 集成后整体 diff 复核。
- 失败日志解释。

## 后续配置建议

在 `config.yaml` 中逐步增加：

```yaml
integration_target_branch: main
integration_worktree_root: .integration-worktrees
integration_runs_root: runs/integration-runs
integration_ai_review_enabled: true
integration_ai_cli_tool: codex
integration_auto_start_after_fix: false
integration_cleanup_after_confirm: true
```

默认保守策略：

- 不自动 push。
- 不自动最终提交。
- 不自动清理失败分支。
- 不自动处理冲突。
- AI 复核失败时不阻塞人工确认，但必须展示风险。
