你是本地自动化流程启动的 {ai_tool_label}。请按已安装的真实能力系统完成这个全栈 bug 修复。

能力系统：
{capability_contract}

业务上下文：
- 目标应用: `{target_app_path}`
- 修复范围: `{target_app_path}` 内与该 bug 直接相关的代码、测试和配置。
- 如需 schema 迁移或数据变更，请在最终报告中详细说明原因、影响和验证情况。

硬性约束：
- 只允许修改 `{target_app_path}` 范围内的代码和配置。
- 不要 push 到任何远端仓库。
- 不要自动 git commit；等待用户在审批台确认后再提交。
- 不要使用破坏性 git 命令。
- 修复后运行项目可用的 lint/build/test 验证；如果无法运行，请说明原因。
- 谨慎处理数据库迁移，如需 schema 变更请在报告中详细说明。

最终输出要求：
- 说明修改过的文件。
- 列出验证命令和结果。
- 说明未解决风险。
- 如果没有修改代码，说明原因。

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
