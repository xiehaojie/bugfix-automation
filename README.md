# Bugfix Automation

本地优先的 AI Bug 修复编排与审批平台。

它可以把 Excel / 在线表格里的 bug 清单转成隔离的 AI 编码任务：每条 bug 创建一个独立 `git worktree` 和 `fix/*` 分支，调用 Codex 或 Claude Code 尝试修复，然后在本地 Web 审批台里查看 diff、日志、验证结果，并由开发者决定通过、重改、拒绝或清理。

它不是 AI IDE，也不会主动 push 代码。它更像是 AI Coding Agent 的任务编排层、隔离执行层、人工审批层和审计层。

## 功能

- 本地 FastAPI + Next.js 审批台。
- 支持 Excel bug 清单、字段映射和筛选规则。
- 每条 bug 一个 Git worktree，互不污染。
- 支持 Codex 和 Claude Code CLI。
- 支持前端、后端、全栈修复提示词模板。
- 支持 diff 审批、AI 日志、补充重改、验证、提交、拒绝和清理。
- SQLite 记录操作历史、AI 会话和日志分段。
- 内置中文 demo 配置、中文 demo Excel、demo 目标仓库，方便第一次跑通。

## 快速开始

```bash
git clone https://github.com/zhaoleizhen/bugfix-automation.git
cd bugfix-automation
python -m pip install -r requirements.txt
cd approval-web && npm install && cd ..
python -m bugfix_automation.cli init --reset-config --reset-runtime
python -m bugfix_automation.cli approval-server
```

打开：

```text
http://127.0.0.1:8765
```

Windows PowerShell：

```powershell
python -m pip install -r requirements.txt
Push-Location approval-web
npm install
Pop-Location
python -m bugfix_automation.cli init --reset-config --reset-runtime
python -m bugfix_automation.cli approval-server
```

也可以直接运行：

```powershell
.\scripts\dev.ps1
```

macOS / Linux：

```bash
./scripts/dev.sh
```

## Demo 体验

默认配置会使用中文示例：

```text
examples/bugs.zh-CN.xlsx
examples/demo-target-repo
```

先看命中的 bug：

```bash
python -m bugfix_automation.cli list
```

只做演练，不调用 AI：

```bash
python -m bugfix_automation.cli list --dry-run
```

演练单条 bug：

```bash
python -m bugfix_automation.cli run-one --row 2 --dry-run
```

真实调用 AI 修一条：

```bash
python -m bugfix_automation.cli run-one --row 2
```

demo 目标仓库里故意留下了两个小问题，方便验证 AI 修复流程：

- 空 bug 列表文案应该显示“暂无待处理 Bug”
- 新增按钮文案应该显示“新增 Bug”

## 常用命令

```bash
python -m bugfix_automation.cli init
python -m bugfix_automation.cli doctor
python -m bugfix_automation.cli list
python -m bugfix_automation.cli list --dry-run
python -m bugfix_automation.cli run-one --row 2
python -m bugfix_automation.cli run-one --issue-id 1
python -m bugfix_automation.cli run-once
python -m bugfix_automation.cli approval-server
python -m bugfix_automation.cli approval-api
```

重置为中文 demo 配置：

```bash
python -m bugfix_automation.cli init --reset-config --reset-runtime
```

生成英文 demo 配置：

```bash
python -m bugfix_automation.cli init --locale en --reset-config --reset-runtime
```

macOS 定时任务：

```bash
python -m bugfix_automation.cli install-launchd --hour 22 --minute 0
```

Windows 和 Linux 暂时建议使用手动运行或系统自带定时器。

## 配置

配置读取优先级：

```text
环境变量 > SQLite 当前配置 > config.yaml > 代码默认值
```

默认中文模板：

```text
config.example.yaml
```

英文模板：

```text
config.example.en.yaml
```

关键配置：

- `excel_path`：bug 清单 `.xlsx` 路径。
- `sheet_name`：工作表名称。
- `assignee`：当前处理人。
- `target_repo`：AI 要修改的目标 Git 仓库。
- `target_app_path`：允许 AI 修改的目标目录。
- `worktree_root`：隔离 worktree 存放目录。
- `cli_tool`：`codex`、`claude` 或 AI CLI 绝对路径。
- `workspaces`：一个或多个项目工作区。
- `filters`：筛选 bug 的规则。
- `excel_profile`：把 Excel 字段映射到统一 bug 字段。

环境变量示例：

```bash
BUGFIX_EXCEL_PATH=/path/to/bugs.xlsx
BUGFIX_TARGET_REPO=/path/to/product-repo
BUGFIX_TARGET_APP_PATH=apps/web
BUGFIX_CLI_TOOL=codex
BUGFIX_APPROVAL_WEB_PORT=8765
BUGFIX_APPROVAL_API_PORT=8766
```

## 安全边界

- 不主动 push 代码。
- 每条 bug 在独立 worktree 中运行。
- AI 运行时会注入本地 Git wrapper，阻止 `git push`。
- 审批和提交只关注 `target_app_path` 范围。
- `logs/`、`runs/`、`uploads/`、`.target-worktrees/`、`data/app.sqlite3` 都不会提交。
- 通过、拒绝、重改、验证、提交都由开发者人工触发。

## 架构

```text
Excel / 在线表格
  -> 字段映射和筛选规则
  -> 渲染 AI Prompt
  -> 创建 Git worktree + fix/* 分支
  -> 调用 Codex / Claude Code
  -> 写入日志和 SQLite 操作历史
  -> FastAPI 审批 API
  -> Next.js 审批台
  -> 通过 / 重改 / 拒绝 / 验证 / 提交
```

核心文件：

- `bugfix_automation/cli.py`：命令入口。
- `bugfix_automation/bootstrap.py`：初始化和环境检查。
- `bugfix_automation/config.py`：配置加载和 YAML 解析。
- `bugfix_automation/runner.py`：批量和单条 bug 执行。
- `bugfix_automation/worktree.py`：Git worktree 隔离和安全边界。
- `bugfix_automation/approval.py`：审批、拒绝、清理、重改。
- `bugfix_automation/api/`：FastAPI 路由。
- `bugfix_automation/storage/schema.sql`：SQLite 表结构。
- `approval-web/`：Next.js 审批台。

## 开发

检查环境：

```bash
python -m bugfix_automation.cli doctor
```

前端构建：

```bash
cd approval-web
npm run build
```

后端测试：

```bash
python -m pytest
```
