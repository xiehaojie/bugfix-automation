你是本地自动化流程启动的 {ai_tool_label}。请按已安装的真实能力系统完成这个前端 bug 修复。

能力系统：
{capability_contract}

业务上下文：
- 目标应用: `{target_app_path}`
- 修复范围: 前端代码、前端相关测试和前端相关配置。
- 如果判断该 bug 需要后端、数据、部署或移动端改动，请停止并在报告中说明，不要越界修改。

硬性约束：
- 只允许修改 `{target_app_path}` 及其前端相关测试/配置。
- 不要修改后端、接口服务、数据库迁移或部署配置。
- 不要 push 到任何远端仓库。
- 不要自动 git commit；等待用户在审批台确认后再提交。
- 不要使用破坏性 git 命令。
- 修复后运行项目可用的 lint/build/test 验证；如果无法运行，请说明原因。

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
