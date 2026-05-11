# 夜间 Bug 自动修复工具

这是一个独立的本地自动化仓库，用来读取桌面上的 `/Users/xiehaojie/Desktop/亦城数智人在线清单.xlsx`，筛选分配给你的前端 bug，然后让 Codex 在每个 bug 独立的 git worktree 中尝试分析、修复、测试，并生成早上审批用的报告和可视化页面。

它只处理前端范围：`/Users/xiehaojie/code/monorepo/apps/pc-web`。

它不会主动 push 到远端。

## 默认配置

- 默认对接人：`谢浩杰`
- 默认 Excel：`/Users/xiehaojie/Desktop/亦城数智人在线清单.xlsx`
- 默认 Sheet：`在线问题清单`
- 目标仓库：`/Users/xiehaojie/code/monorepo`
- 前端范围：`apps/pc-web`
- 修复工作目录：本自动化仓库下的 `.target-worktrees/`
- 定时任务：每天晚上 22:00

可通过环境变量覆盖：

```bash
BUGFIX_EXCEL_PATH=/path/to/list.xlsx
BUGFIX_ASSIGNEE=谢浩杰
BUGFIX_TARGET_REPO=/Users/xiehaojie/code/monorepo
BUGFIX_TARGET_APP_PATH=apps/pc-web
BUGFIX_WORKTREE_ROOT=/Users/xiehaojie/code/bugfix-automation/.target-worktrees
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

启动本地可视化审批台：

```bash
python3 -m bugfix_automation.cli approval-server
```

启动后打开：

```text
http://127.0.0.1:8765
```

审批台会在启动时输出“当前有多少个修改待处理”。页面中每个 `fix/*` 分支都会显示类似 GitHub 的代码比对、改动文件、通过审批并提交、拒绝并删除。

安装 macOS 每天 22:00 的本地定时任务：

```bash
python3 -m bugfix_automation.cli install-launchd
```

定时任务日志会写到：

- `logs/launchd.out.log`
- `logs/launchd.err.log`

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
- 早上可以逐条看 diff，决定通过还是拒绝
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

## 早上怎么审批

推荐使用可视化审批台：

```bash
cd /Users/xiehaojie/code/bugfix-automation
python3 -m bugfix_automation.cli approval-server
```

然后打开：

```text
http://127.0.0.1:8765
```

你会看到：

- 当前有多少个待处理修改
- 每个 bug 对应的本地 `fix/*` 分支
- 改动文件列表
- 类似 GitHub 的代码比对
- “审批通过并提交”
- “拒绝并删除”

如果不想打开页面，也可以看：

```text
runs/YYYY-MM-DD/approval.md
```

自动化不会把修复合并进你的主分支。你通过审批后，修复会保留在对应的本地 `fix/*` 分支中，后续你可以在 pc-web 的 Git 工具里继续 cherry-pick、merge 或自己处理。

## 冲突怎么处理

多条 bug 如果修改了同一个文件，报告会标出冲突风险。建议逐条审批：

1. 先看每条 bug 的截图、问题描述和 diff。
2. 如果两条 bug 改了同一个文件，先确认它们是否是同一块逻辑。
3. 选择一个分支先合入或 cherry-pick。
4. 第二个分支再重新对比，必要时手动处理冲突。

这种模式会比直接让所有 bug 改在同一个工作区里更稳，因为每个 bug 的原始改动都还在独立分支中。
