# 本地 PR 合并队列设计

## 背景

自动修复流程会为每个 bug 生成独立的 `fix/*` 分支和 worktree。AI 修改完成后，当前主要操作是切到一个目标分支，把多个 AI 已修好的分支逐个合并到目标分支上，先不提交，手动验证整体效果，确认后再提交并清理已合并分支。

这套操作本质上类似一个本地 Pull Request 队列：每个 `fix/*` 分支是一个待合入 PR，目标分支是 base branch，人工确认后合并并删除 source branch。目标是把这套机械流程自动化，同时保留人工最终确认权。

## 目标

- 支持选择目标分支，将多个 `fix/*` 分支自动集成到一个临时集成分支中。
- 集成过程默认不提交到用户目标分支，先生成可验证的集成 worktree。
- 对每个来源分支记录应用状态、来源 commit、改动文件、验证结果和 AI 复核结论。
- 支持在 AI 修改完成后由 AI-cli 工具参与验证和总结，用户打开审批台即可查看集成单。
- 用户确认后生成最终提交，并删除已成功合入的 `fix/*` 分支及对应 worktree。
- 失败、冲突、验证不通过的分支必须保留，方便继续重做或人工处理。

## 非目标

- 第一版不自动 push 到远端。
- 第一版不自动决定最终提交，必须等待用户确认。
- 第一版不要求完全替代人工验证，只负责把机械合并、基础验证、AI 复核和记录自动化。
- 第一版不处理复杂跨仓库联动，只面向当前 `workspaces` 中配置的单个目标仓库和应用路径。

## 推荐方案

新增“集成单 Integration Run”概念。一次集成单代表一批 `fix/*` 分支针对某个目标分支的本地合并预演。

示例：

```text
目标分支: main
集成分支: integration/pc-web-main-20260520-0900
集成 worktree: .integration-worktrees/pc-web-main-20260520-0900
来源分支:
- fix/24-收藏夹中展示的收藏列表展示的skill
- fix/37-可能会接收到多个重复待办希望能够帮我
- fix/15-移动端个人空间进行文件类型筛选操作页
```

集成完成后，用户在审批台查看这张集成单。确认通过后，系统在集成分支上创建最终 commit，并删除成功合入的来源分支。

## 修复完成后集成流程

1. 自动修复任务完成后，`fix/*` 分支进入待审批状态。
2. 集成任务根据配置或用户选择确定目标分支和待集成分支。
3. 系统创建独立集成 worktree，并从目标分支拉出 `integration/*` 临时分支。
4. 系统按顺序应用每个 `fix/*` 分支。
5. 每应用一个分支后记录结果：
   - 来源分支
   - 来源 commit 或 diff 指纹
   - 应用方式
   - 应用状态
   - 改动文件
   - 冲突或失败原因
6. 全部可应用分支处理后运行 `verify_commands`。
7. 调用 AI-cli 工具读取 bug 描述、diff、验证日志，生成复核摘要。
8. 将结果写入集成单 JSON 和 Markdown 报告。

## 人工确认流程

1. 用户打开审批台，进入“集成预演”页面。
2. 页面展示待确认的集成单：
   - 目标分支
   - 集成分支
   - 集成 worktree 路径
   - 成功应用的分支
   - 冲突或失败分支
   - 最终累计 diff
   - 验证命令结果
   - AI 复核摘要
3. 用户在本地打开集成 worktree 或由页面提供项目启动入口进行人工验证。
4. 用户确认无误后点击“确认提交”。
5. 系统生成最终 commit。
6. 系统删除已成功合入且已记录的 `fix/*` 分支及对应 worktree。
7. 冲突、失败、未合入的分支继续保留在审批台，后续可重做或人工处理。

## Git 策略

优先使用确定性脚本执行 Git 操作，AI-cli 不直接自由执行合并和删除。

### 有提交的 fix 分支

如果 `fix/*` 分支上已经有提交，使用：

```bash
git cherry-pick -n <commit>
```

这样可以把改动叠加到集成分支，但不立即生成提交。

### 未提交的 fix worktree

如果 `fix/*` 分支仍是未提交改动，使用对应 worktree 的 diff：

```bash
git diff --binary -- <target_app_path>
git apply --3way
```

系统需要自动判断分支是否已有 commit、是否存在未提交 diff，并记录实际使用的应用方式。

### 最终提交

用户确认后，在集成分支上生成一个最终提交。提交信息应保留来源信息：

```text
fix(pc-web): batch apply AI bug fixes

Included fixes:
- fix/24-收藏夹中展示的收藏列表展示的skill (abc1234)
- fix/37-可能会接收到多个重复待办希望能够帮我 (def5678)

Integration run: 20260520-0900
Verified: lint passed, build passed
```

## 分支清理规则

只有满足以下条件的来源分支才允许删除：

- 已成功应用到集成单。
- 用户已确认最终提交。
- 集成单记录了来源分支和来源 commit 或 diff 指纹。
- 最终提交已成功创建。
- 删除前再次确认该来源分支仍是本地 `fix/*` 分支。

删除内容：

- 对应 `fix/*` 本地分支。
- 对应 `.target-worktrees/*` worktree。

不删除内容：

- 冲突分支。
- 验证失败分支。
- 用户手动标记为保留的分支。
- 非 `fix/*` 分支。

## AI-cli 角色

AI-cli 参与验证和总结，不直接拥有最终合并权限。

推荐分三类角色：

### merge-orchestrator

确定性 Python 代码负责：

- 创建 integration worktree。
- 应用分支 diff 或 cherry-pick。
- 检测冲突。
- 运行验证命令。
- 写入集成单状态。
- 在用户确认后提交和清理分支。

### ai-verify-agent

AI-cli 负责：

- 阅读 bug 原始描述。
- 阅读每个来源分支 diff。
- 阅读验证命令日志。
- 判断改动是否覆盖问题描述。
- 输出“建议通过 / 建议人工复查 / 阻塞”的摘要。

### browser/e2e-agent

可选增强能力：

- 启动本地项目。
- 根据 bug 描述访问相关页面。
- 截图或记录页面状态。
- 给出页面级验证结论。

第一版可以先不做完整 E2E，只保留 AI 对 diff 和日志的复核。

## 数据模型

集成单保存到 `runs/integration-runs/<run_id>/integration-run.json`。

建议结构：

```json
{
  "run_id": "20260520-0900-pc-web-main",
  "workspace_id": "pc-web",
  "target_branch": "main",
  "integration_branch": "integration/pc-web-main-20260520-0900",
  "integration_worktree": ".integration-worktrees/pc-web-main-20260520-0900",
  "status": "pending-user-approval",
  "items": [
    {
      "branch": "fix/24-收藏夹中展示的收藏列表展示的skill",
      "source_commit": "abc1234",
      "apply_method": "cherry-pick-no-commit",
      "status": "applied",
      "changed_files": ["apps/pc-web/src/example.tsx"],
      "error": ""
    }
  ],
  "verify": {
    "status": "passed",
    "commands": [
      {
        "command": "npm run lint",
        "status": "passed",
        "log_path": "runs/integration-runs/20260520-0900-pc-web-main/lint.log"
      }
    ]
  },
  "ai_review": {
    "status": "suggest-pass",
    "summary": "已应用的改动与问题描述基本匹配，未发现明显回归风险。"
  },
  "final_commit": "",
  "created_at": "2026-05-20T09:00:00+08:00",
  "updated_at": "2026-05-20T09:30:00+08:00"
}
```

同时生成 Markdown 报告，方便直接查看或归档。

## 审批台设计

新增“集成预演”区域。

第一版页面能力：

- 选择目标分支。
- 选择待集成的 `fix/*` 分支。
- 调整应用顺序。
- 创建集成单。
- 查看集成单列表。
- 查看单个集成单详情。
- 查看最终累计 diff。
- 查看验证日志。
- 查看 AI 复核摘要。
- 确认提交。
- 删除已合入来源分支。

状态文案：

- `draft`: 已创建，未开始。
- `running`: 正在集成。
- `blocked`: 有冲突或阻塞错误。
- `verify-failed`: 集成成功但验证失败。
- `pending-user-approval`: 等待人工确认。
- `committed`: 已确认提交。
- `cleaned`: 已提交并清理来源分支。

## API 设计

建议新增接口：

```text
GET  /api/integration-runs
GET  /api/integration-runs/{run_id}
POST /api/integration-runs
POST /api/integration-runs/{run_id}/start
POST /api/integration-runs/{run_id}/confirm
POST /api/integration-runs/{run_id}/cleanup
POST /api/integration-runs/{run_id}/abort
```

`POST /api/integration-runs` 请求体：

```json
{
  "workspace_id": "pc-web",
  "target_branch": "main",
  "branches": [
    "fix/24-收藏夹中展示的收藏列表展示的skill",
    "fix/37-可能会接收到多个重复待办希望能够帮我"
  ]
}
```

## 错误处理

### 合并冲突

- 立即停止当前分支应用。
- 记录冲突文件和 Git 输出。
- 将集成单标记为 `blocked`。
- 保留集成 worktree，方便人工进入处理。
- 不删除任何来源分支。

### 验证失败

- 保留已应用结果。
- 标记为 `verify-failed`。
- 展示失败命令和日志路径。
- 不允许直接清理来源分支，除非用户明确确认继续。

### AI 复核失败

- 不阻断 Git 结果。
- 标记为 `pending-user-approval`，但显示“AI 复核未完成/失败”。
- 用户仍可人工确认。

### 用户取消

- 删除 integration worktree。
- 删除 integration 临时分支。
- 保留所有 `fix/*` 来源分支。

## 安全边界

- 所有 Git 写操作限定在配置的 `target_repo` 内。
- 所有应用 diff 限定在 `target_app_path` 范围内。
- 不允许删除非 `fix/*` 分支。
- 不自动 push。
- 不自动提交到用户正在工作的真实分支。
- AI-cli 不拥有最终提交和清理权限。

## MVP 实施顺序

1. 后端集成服务：
   - 创建 integration worktree。
   - 应用多个 `fix/*` 分支。
   - 运行 `verify_commands`。
   - 写入 `integration-run.json`。

2. CLI：
   - `integration create`
   - `integration start`
   - `integration confirm`
   - `integration cleanup`

3. 审批台只读展示：
   - 集成单列表。
   - 集成详情。
   - 验证日志。
   - 累计 diff。

4. 审批台操作按钮：
   - 创建集成单。
   - 开始集成。
   - 确认提交。
   - 清理来源分支。

5. AI-cli 复核：
   - 读取 diff 和日志。
   - 写入 `ai_review`。
   - 在审批台展示摘要。

6. 可选浏览器验证：
   - 启动项目。
   - 针对重点 bug 执行页面验证。
   - 保存截图和结论。

## 测试策略

后端测试：

- 能创建独立 integration worktree。
- 能对有 commit 的 `fix/*` 分支执行 `cherry-pick -n`。
- 能对未提交 worktree diff 执行 `git apply --3way`。
- 冲突时正确停止并记录状态。
- 验证命令失败时正确标记 `verify-failed`。
- 确认提交后写入 final commit。
- 只删除已成功合入且已确认的 `fix/*` 分支。
- 不删除失败分支和非 `fix/*` 分支。

前端测试：

- 集成单列表正确展示不同状态。
- 集成详情能展示分支、diff、日志和 AI 摘要。
- 确认提交和清理操作有明确状态反馈。
- 冲突和验证失败状态不能被误展示为可安全清理。

## 默认决策与可配置项

第一版按以下默认行为实现：

- 默认目标分支通过配置项 `integration_target_branch` 指定；未配置时使用当前仓库分支。
- 默认排序按 Excel 行号升序；没有 Excel 记录时按分支创建时间升序。
- 最终提交生成一个批量 commit。
- AI 复核复用现有 `cli_tool`。
- 确认提交并清理来源分支后，自动标记对应 Excel 行为已处理。

后续可扩展为页面配置项：

- 目标分支选择。
- 分支应用顺序拖拽调整。
- 批量 commit 或逐 bug commit。
- 独立的 `integration_ai_cli_tool`。
- 确认提交后是否自动更新 Excel 状态。
