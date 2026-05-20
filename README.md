# 夜间 Bug 自动修复工具

这是一个独立的本地自动化仓库，用来读取 Excel bug 清单，筛选分配给你的前端 bug，然后让 Codex 在每个 bug 独立的 git worktree 中尝试分析、修复、测试，并在早上提供一个 Next 审批工作台。

默认工作区处理前端范围：`/Users/xiehaojie/code/monorepo/apps/pc-web`。也可以在 `config.yaml` 的 `workspaces` 中增加其他项目。

它不会主动 push 到远端。

## 依赖安装

后端审批 API 使用 FastAPI，首次运行前先安装 Python 依赖：

```bash
python3 -m pip install -r requirements.txt
```

审批台前端依赖仍在 `approval-web/package.json` 中；启动 `approval-server` 时如果没有 `node_modules`，工具会自动在 `approval-web` 里执行 `npm install`。

## 配置入口

优先改仓库根目录的 [config.yaml](/Users/xiehaojie/code/bugfix-automation/config.yaml)：

```yaml
excel_path: /Users/xiehaojie/Desktop/亦城数智人在线清单.xlsx
sheet_name: 在线问题清单
assignee: 谢浩杰
active_workspace: pc-web
max_concurrency: 2

target_repo: /Users/xiehaojie/code/monorepo
target_app_path: apps/pc-web

worktree_root: .target-worktrees
runs_root: runs
logs_root: logs

launchd_label: local.bugfix-automation.nightly
cli_tool: codex

approval_web_port: 8765
approval_api_port: 8766

excel_processed_status_column: 对接人状态
excel_processed_status_value: 已处理

workspaces:
  - id: pc-web
    name: PC Web
    target_repo: /Users/xiehaojie/code/monorepo
    target_app_path: apps/pc-web
    scope_paths: apps/pc-web
    verify_commands: npm run lint,npm run build
    prompt_context_paths:
    max_concurrency: 2

filters:
  - field: 对接人
    op: equals
    value: 谢浩杰
  - field: 对接人状态
    op: not_in
    values: 已解决,已处理
  - field: 来源系统
    op: in
    values: 小亦PC,小亦APP
  - field: 提出人状态
    op: in
    values: 待处理,处理中

prompt:
  fields: 序号,来源系统,一级分类,二级分类,优先级,提出人,提出日期,提出人状态,对接人,对接人状态,解决日期,问题描述,备注,备注2
  template: 请优先修复前端可独立完成的问题；如果需要后端或数据改造，请停止并说明原因。
  context_paths:

schedule:
  hour: 22
  minute: 0
```

环境变量优先级更高，适合临时覆盖：

```bash
BUGFIX_EXCEL_PATH=/path/to/list.xlsx
BUGFIX_ASSIGNEE=谢浩杰
BUGFIX_TARGET_REPO=/Users/xiehaojie/code/monorepo
BUGFIX_TARGET_APP_PATH=apps/pc-web
BUGFIX_WORKTREE_ROOT=/Users/xiehaojie/code/bugfix-automation/.target-worktrees
BUGFIX_SCHEDULE_HOUR=22
BUGFIX_SCHEDULE_MINUTE=0
BUGFIX_APPROVAL_WEB_PORT=8765
BUGFIX_APPROVAL_API_PORT=8766
BUGFIX_EXCEL_PROCESSED_STATUS_COLUMN=对接人状态
BUGFIX_EXCEL_PROCESSED_STATUS_VALUE=已处理
BUGFIX_CLI_TOOL=codex
```

配置读取顺序是：

```text
环境变量 > config.yaml > 代码默认值
```

`excel_path` 只是默认读取位置。更推荐在审批台里直接上传当天的 xlsx，上传后文件会保存到自动化仓库的 `uploads/` 目录，并自动把 `config.yaml` 的 `excel_path` 改成新文件。

## 筛选规则

Excel 过滤现在由 `config.yaml` 的 `filters` 配置决定。默认规则是：

- `对接人` 等于配置的对接人，默认是 `谢浩杰`
- `对接人状态` 不是 `已解决`，也不是配置里的已处理状态，默认 `已处理`
- `来源系统` 是 `小亦PC` 或 `小亦APP`
- `提出人状态` 是 `待处理` 或 `处理中`

支持的 `op`：

- `equals`
- `not_equals`
- `in`
- `not_in`
- `non_empty`
- `empty`

每一行就是一个 bug。工具会提取问题描述、备注、一级分类、二级分类、状态、日期等字段，也会提取 `截图1` / `截图2` / `截图3` 单元格中的 WPS `DISPIMG` 图片，并把截图传给 Codex。

## 工作区和提示词

`workspaces` 用来切换不同项目。审批台顶部可以切换已有工作区；新增工作区时先编辑 `config.yaml`：

- `id`：工作区唯一标识
- `name`：页面展示名
- `target_repo`：目标 git 仓库
- `target_app_path`：允许 Codex 修改和审批的工程目录
- `verify_commands`：每条 bug 修完后要运行的检查命令
- `prompt_context_paths`：默认放进提示词的工程文件或目录
- `max_concurrency`：该工作区建议并发数

`prompt.fields` 控制哪些 Excel 字段进入 Codex 提示词；`prompt.template` 是初始化提示词；`prompt.context_paths` 可以补充工程内重点文件或目录。审批台右侧也可以直接调整这些配置。

## 并发执行

定时任务和“立即执行一次”会按 `max_concurrency` 并发处理 Excel 命中的 bug。每条 bug 使用独立 worktree 和独立分支，因此可以并行跑；默认并发是 `2`，建议日常保持 `2-3`，不建议超过 `4`，因为 Codex、lint、build 会同时占用 CPU、内存和磁盘 IO。

已处理或已存在工作区的任务会跳过：

- Excel 行已被标记为配置的已处理状态
- 对应 worktree 已存在
- 对应 `fix/*` 分支已存在
- 分支已经在某个 worktree 中检出

## 常用命令

先进入自动化仓库：

```bash
cd /Users/xiehaojie/code/bugfix-automation
```

列出当前 Excel 中符合筛选规则的 bug：

```bash
python3 -m bugfix_automation.cli list
```

只生成演练报告，不启动 Codex：

```bash
python3 -m bugfix_automation.cli list --dry-run
```

只跑 Excel 第 46 行这一条 bug：

```bash
python3 -m bugfix_automation.cli run-one --row 46
```

只跑 `序号` 为 1 的 bug：

```bash
python3 -m bugfix_automation.cli run-one --issue-id 1
```

手动跑一次所有符合筛选规则的 bug：

```bash
python3 -m bugfix_automation.cli run-once
```

启动 Next 审批台：

```bash
python3 -m bugfix_automation.cli approval-server
```

启动后打开：

```text
http://127.0.0.1:8765
```

第一次启动审批台会自动进入 `approval-web` 执行 `npm install`。后续会直接启动。

只启动审批 API：

```bash
python3 -m bugfix_automation.cli approval-api
```

安装 macOS 每天 22:00 的本地定时任务：

```bash
python3 -m bugfix_automation.cli install-launchd
```

安装或更新为自定义时间：

```bash
python3 -m bugfix_automation.cli install-launchd --hour 21 --minute 30
```

定时任务日志会写到：

- `logs/launchd.out.log`
- `logs/launchd.err.log`

## 审批台功能

审批台由两部分组成：

- Python 本地 API：默认 `http://127.0.0.1:8766`
- Next 16 前端：默认 `http://127.0.0.1:8765`

页面提供：

- 左侧待审批分支列表和待处理数量
- 实时读取 Excel，并列出当前命中筛选规则的 bug
- 如果 Excel 行里有 `截图1` / `截图2` / `截图3`，会显示截图缩略图，点击可打开原图
- 展示定时任务状态、每天执行时间、LaunchAgent 路径
- 前端按钮开启、取消、更新定时任务时间
- 前端按钮立即手动执行一次完整自动化
- 前端上传当天 Excel，并自动切换当前读取文件
- 顶部切换当前工作区
- 右侧配置提示词字段、初始化提示词、工程上下文路径和最高并发数
- 展示当前选中分支的 Codex 执行日志
- 已无 diff 但 worktree 仍残留的分支列表
- 改动文件列表
- 类似 GitHub 的代码比对
- 通过并提交
- 拒绝删除
- 清理残留 worktree
- 重新修改

页面会在打开时读取一次 Excel，之后每 30 秒自动刷新一次；也可以点击“刷新状态”手动刷新。Excel 筛选结果表会展示序号、Excel 行号、截图、来源系统、一级/二级分类、提出人状态、对接人状态、问题描述、备注和对应 `fix/*` 分支名。截图会导出到 `runs/approval-images/`，只通过本地 API 访问。

定时任务面板里的“保存并开启”会按页面输入的时间安装或重新加载 macOS LaunchAgent；“取消定时”会卸载并删除对应 plist；“立即执行一次”会在后台启动 `run-once`，日志写入 `logs/manual-run-*.log`。

Bug 文档面板里的“上传并切换”会把 xlsx 复制到：

```text
/Users/xiehaojie/code/bugfix-automation/uploads/
```

然后更新 `config.yaml` 的 `excel_path`。之后审批台、手动执行和晚上定时执行都会读取这份上传后的文件。

重新修改可以补充：

- 文字说明
- 本机文件路径
- 本机图片路径

图片路径会作为 `codex exec --image` 传给 Codex；文件路径会写入 prompt，让 Codex 按路径读取上下文。

Codex 执行日志会写到：

```text
logs/codex/<fix-branch>.log
```

审批台右侧“Codex 日志”会展示当前选中分支的日志，并随页面自动刷新。

夜间自动化只会生成独立 worktree 中的待审批 diff，不会提前 commit 目标项目。审批通过后才会：

1. 只 stage `apps/pc-web`
2. 在对应 `fix/*` 分支本地 commit
3. 移除该 bug 的 worktree
4. 保留本地 `fix/*` 分支和 commit
5. 将 Excel 对应行的 `对接人状态` 改为 `已处理`
6. 不 push

这里的“提交”只表示在目标 monorepo 的对应 `fix/*` 分支本地 commit，方便你后续对比和合并；不会 push 到远端。

自动化仓库本身不会再由 Codex 主动提交。除非你明确说“提交自动化仓库改动”，否则我只会保留工作区改动给你检查。

Excel 状态更新会直接修改 xlsx 内部的 sheet XML，不使用 openpyxl 重写整本工作簿，尽量避免破坏 WPS 的 `DISPIMG` 截图信息。

## worktree 是怎么用的

你的主项目在：

```text
/Users/xiehaojie/code/monorepo
```

自动化不会直接在你平时打开的主目录里改代码。它会为每个 bug 单独创建一个目标仓库的 worktree，例如：

```text
/Users/xiehaojie/code/bugfix-automation/.target-worktrees/fix-1-个人空间上传附件页面反馈不够明显
```

这个目录本质上是同一个 monorepo 的另一个工作副本，但不是复制一份完整 `.git` 仓库。它共用主仓库的对象数据库，只给这个分支单独准备一份工作目录，例如：

```text
fix/1-个人空间上传附件页面反馈不够明显
```

这样做的目的：

- 每条 bug 的改动彼此隔离，不会互相覆盖
- 不影响你正在使用的主 monorepo 工作区
- 早上可以逐条看 diff，决定通过、重改还是拒绝
- 多条 bug 如果改了同一个文件，报告会提示冲突风险

你的自动化项目目录不需要长期放在 `.worktrees/` 里。`.worktrees/` 只是临时隔离开发时使用的目录；当前自动化仓库的正式代码就在：

```text
/Users/xiehaojie/code/bugfix-automation
```

目标 monorepo 的 bug 修复 worktree 默认放在：

```text
/Users/xiehaojie/code/bugfix-automation/.target-worktrees/
```

如果你不想在 VS Code 里看到这些临时目录，可以只打开自动化仓库根目录，或者把 `.target-worktrees/` 保持折叠；它不属于需要日常编辑的代码。

## 分支命名

修复分支会按下面格式命名：

```text
fix/序号-中文问题摘要
```

例子：

```text
fix/1-个人空间上传附件页面反馈不够明显
```

中文摘要来自 Excel 的 `问题描述`，会做长度和非法字符处理。

## 安全限制

自动化有几层限制，尽量避免误伤主项目：

- Codex 子进程只在对应 bug 的 worktree 中运行
- Codex 命令使用 `--sandbox workspace-write`
- 自动化不会修改目标 monorepo 的 git hooks 或 git config
- Codex 子进程的 `PATH` 会临时插入一个本地 `git` 包装器，用来阻止 `git push`
- 修复前后都会检查改动范围，发现 `apps/pc-web` 以外的业务代码改动会失败
- 审批通过时只会 stage `apps/pc-web`
- 审批通过只在本地提交，不会 push
- `approval-web/node_modules/`、`.next/`、`logs/`、`runs/`、`uploads/` 都在 `.gitignore` 中，不会被提交；如果 VS Code Source Control 里看到这些目录，先刷新 Git 视图，命令行 `git status --short` 才是最终判断。

## 输出文件

每次运行会生成：

- `runs/YYYY-MM-DD/report.json`
- `runs/YYYY-MM-DD/report.md`
- `runs/YYYY-MM-DD/approval.md`
- `runs/YYYY-MM-DD/images/<分支名>/...`
- `logs/codex/<fix-branch>.log`

`report.json` 适合程序读取，`report.md` 是普通运行报告，`approval.md` 是早上人工审批报告。

## 冲突怎么处理

多条 bug 如果修改了同一个文件，报告会标出冲突风险。建议逐条审批：

1. 先看每条 bug 的截图、问题描述和 diff。
2. 如果两条 bug 改了同一个文件，先确认它们是否是同一块逻辑。
3. 选择一个分支先合入或 cherry-pick。
4. 第二个分支再重新对比，必要时手动处理冲突。

这种模式会比直接让所有 bug 改在同一个工作区里更稳，因为每个 bug 的原始改动都还在独立分支中。
