你是本地自动化流程启动的 {ai_tool_label}。请使用项目级子智能体协同完成这个全栈 bug 修复：

1. 先委派 bug-triage-agent 分析 Excel 行内容，判断问题涉及前端、后端还是两者，并定位可能区域。
2. 再委派 fix-agent 修改 `{target_app_path}` 下的相关代码（前后端均可修改）。
3. 再委派 verification-agent 运行验证并检查回归风险。
4. 最后委派 branch-commit-agent 整理本地分支状态、改动摘要和建议提交信息；不要自动提交。

硬性约束：
- 只允许修改 `{target_app_path}` 范围内的代码和配置。
- 不要 push 到任何远端仓库。
- 不要自动 git commit；等待用户在审批台确认后再提交。
- 不要使用破坏性 git 命令。
- 修复后运行项目可用的 lint/build/test 验证。
- 谨慎处理数据库迁移，如需 schema 变更请在报告中详细说明。

Excel 信息：
- Excel 行号: {excel_row}
- 序号: {issue_id}
- 工作区: {workspace_name}

配置提示词：
{prompt_template}

Excel 选中字段：
{selected_lines}

原始 Excel 行完整信息：
{raw_lines}

随本次 {ai_tool_label} 调用传入的截图：
{image_lines}

需要优先阅读的工程文件/目录：
{context_lines}
