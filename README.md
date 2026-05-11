# 夜间 Bug 自动修复工具

这是一个独立的本地自动化仓库，用来读取桌面上的 `/Users/xiehaojie/Desktop/亦城数智人在线清单.xlsx`，筛选分配给你的前端 bug，然后让 Codex 在每个 bug 独立的 git worktree 中尝试分析、修复、测试，并在早上提供一个 Next 审批工作台。

它只处理前端范围：`/Users/xiehaojie/code/monorepo/apps/pc-web`。

它不会主动 push 到远端。

## 配置入口

优先改仓库根目录的 [config.yaml](/Users/xiehaojie/code/bugfix-automation/config.yaml)：

```yaml
excel_path: /Users/xiehaojie/Desktop/亦城数智人在线清单.xlsx
sheet_name: 在线问题清单
assignee: 谢浩杰

target_repo: /Users/xiehaojie/code/monorepo
target_app_path: apps/pc-web

worktree_root: .target-worktrees
runs_root: runs
logs_root: logs

launchd_label: local.bugfix-automation.nightly
codex_bin: codex

approval_web_port: 8765
approval_api_port: 8766

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
BUGFIX_CODEX_BIN=codex
```

配置读取顺序是：

```text
环境变量 > config.yaml > 代码默认值
```

## 筛选规则

Excel 中的行必须同时满足：

- `对接人` 等于配置的对接人，默认是 `谢浩杰`
- `对接人状态` 不是 `已解决`
- `来源系统` 是 `小亦PC` 或 `小亦APP`
- `提出人状态` 是 `待处理` 或 `处理中`

每一行就是一个 bug。工具会提取问题描述、备注、一级分类、二级分类、状态、日期等字段，也会提取 `截图1` / `截图2` / `截图3` 单元格中的 WPS `DISPIMG` 图片，并把截图传给 Codex。

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

定时任务日志会写到：

- `logs/launchd.out.log`
- `logs/launchd.err.log`

## 审批台功能

审批台由两部分组成：

- Python 本地 API：默认 `http://127.0.0.1:8766`
- Next 16 前端：默认 `http://127.0.0.1:8765`

页面提供：

- 左侧待审批分支列表和待处理数量
- 已无 diff 但 worktree 仍残留的分支列表
- 改动文件列表
- 类似 GitHub 的代码比对
- 通过并提交
- 拒绝删除
- 清理残留 worktree
- 重新修改

重新修改可以补充：

- 文字说明
- 本机文件路径
- 本机图片路径

图片路径会作为 `codex exec --image` 传给 Codex；文件路径会写入 prompt，让 Codex 按路径读取上下文。

审批通过后会：

1. 只 stage `apps/pc-web`
2. 在对应 `fix/*` 分支本地 commit
3. 移除该 bug 的 worktree
4. 保留本地 `fix/*` 分支和 commit
5. 不 push

## worktree 是怎么用的

你的主项目在：

```text
/Users/xiehaojie/code/monorepo
```

自动化不会直接在你平时打开的主目录里改代码。它会为每个 bug 单独创建一个目标仓库的 worktree，例如：

```text
/Users/xiehaojie/code/bugfix-automation/.target-worktrees/fix-1-个人空间上传附件页面反馈不够明显
```

这个目录本质上是同一个 monorepo 的另一个工作副本，但它检出的是独立分支，例如：

```text
fix/1-个人空间上传附件页面反馈不够明显
```

这样做的目的：

- 每条 bug 的改动彼此隔离，不会互相覆盖
- 不影响你正在使用的主 monorepo 工作区
- 早上可以逐条看 diff，决定通过、重改还是拒绝
- 多条 bug 如果改了同一个文件，报告会提示冲突风险

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

## 输出文件

每次运行会生成：

- `runs/YYYY-MM-DD/report.json`
- `runs/YYYY-MM-DD/report.md`
- `runs/YYYY-MM-DD/approval.md`
- `runs/YYYY-MM-DD/images/<分支名>/...`

`report.json` 适合程序读取，`report.md` 是普通运行报告，`approval.md` 是早上人工审批报告。

## 冲突怎么处理

多条 bug 如果修改了同一个文件，报告会标出冲突风险。建议逐条审批：

1. 先看每条 bug 的截图、问题描述和 diff。
2. 如果两条 bug 改了同一个文件，先确认它们是否是同一块逻辑。
3. 选择一个分支先合入或 cherry-pick。
4. 第二个分支再重新对比，必要时手动处理冲突。

这种模式会比直接让所有 bug 改在同一个工作区里更稳，因为每个 bug 的原始改动都还在独立分支中。
