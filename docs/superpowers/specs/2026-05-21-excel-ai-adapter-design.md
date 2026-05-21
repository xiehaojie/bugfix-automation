# Excel AI 智能适配设计

## 背景

当前自动化流程已经能把 Excel 首行表头映射成每行 `dict`，也能在审批台中选择筛选字段和传给 AI 的字段。真正限制适配性的地方在后续业务归一化：`BugRecord` 仍固定读取 `序号`、`来源系统`、`一级分类`、`问题描述`、`备注` 等中文列名。

这导致换一份 Excel 模板后，即使表头能读出来，列表展示、分支名、筛选结果、提示词摘要和历史导入记录也会退化或丢失关键语义。

目标是让用户上传任意结构相近的 bug Excel 后，可以用 AI 快速生成字段映射和该 Excel 专用的修复提示词，再由用户确认保存。后续夜间批量执行仍使用确定性配置，保证可复现、可调试、可回退。

## 目标

- 支持 AI 根据当前 Excel 的表头和少量样例行生成字段映射。
- 支持 AI 同时生成这张 Excel 专用的 prompt 模板。
- 支持 AI 推荐传给 Codex 的 Excel 字段、分支摘要字段和筛选规则。
- 用户可以在审批台预览、编辑、保存 AI 生成的适配配置。
- `filter_bugs` 通过配置把任意 Excel 行归一化为标准 `BugRecord`。
- `render_codex_prompt` 保留标准字段，同时把原始 Excel 行信息完整传给 AI，避免字段映射漏掉上下文。
- 保持当前默认配置兼容，不破坏已有 `亦城数智人在线清单.xlsx` 使用方式。

## 非目标

- 第一版不让每一行都实时调用 AI 生成完整修复 prompt。
- 第一版不自动执行 AI 生成的配置，必须先由用户确认保存。
- 第一版不训练或缓存复杂模型，只调用本机配置的 `cli_tool`。
- 第一版不要求识别所有 Excel 类型，只面向“首行为表头、每行表示一个 bug 或需求”的表格。
- 第一版不改变 Excel 图片导出逻辑，截图仍通过现有 `bug.raw` 和图片列处理。

## 推荐方案

新增“Excel 智能适配配置”。AI 负责读懂表结构和生成建议，代码负责稳定批跑。

配置示例：

```yaml
excel_profile:
  canonical_fields:
    issue_id: 序号
    description: 问题描述
    source_system: 来源系统
    priority: 优先级
    primary_category: 一级分类
    secondary_category: 二级分类
    requester: 提出人
    request_date: 提出日期
    requester_status: 提出人状态
    assignee: 对接人
    assignee_status: 对接人状态
    resolved_date: 解决日期
    remark: 备注
    remark2: 备注2
  prompt:
    fields:
      - 问题描述
      - 备注
      - 备注2
    template: |
      请优先根据当前 Excel 的业务语义修复前端可独立完成的问题。
      如果描述中包含复现路径、期望效果或截图说明，必须优先使用这些信息。
    branch_summary_fields:
      - 问题描述
      - 一级分类
```

如果没有 `excel_profile`，系统使用当前硬编码列名作为默认映射，保持现有行为。

## 数据流

### AI 识别流程

1. 用户上传或选择 Excel。
2. 前端调用 `/api/excel/adapter/analyze`。
3. 后端读取当前 sheet 的表头和前几行非空样例。
4. 后端把表头、样例行、当前工作区名称、当前筛选规则、当前 prompt 配置传给 `cli_tool`。
5. AI 返回结构化 JSON：
   - `canonical_fields`
   - `prompt.fields`
   - `prompt.template`
   - `branch_summary_fields`
   - `filters`
   - `warnings`
6. 后端校验 JSON，只保留当前 Excel 真实存在的列名。
7. 前端展示识别结果，用户可以编辑后保存。
8. 前端调用 `/api/excel/adapter/save`，后端写入 `config.yaml`。

### 执行流程

1. `read_sheet` 继续读取原始 Excel 行。
2. `filter_bugs` 读取 `config.excel_profile.canonical_fields`。
3. 每行通过字段映射归一化为 `BugRecord`。
4. 筛选规则仍使用原始 Excel 表头，兼容现有筛选编辑器。
5. 分支名使用 `excel_profile.prompt.branch_summary_fields` 或现有 `branch_summary_fields`。
6. `render_codex_prompt` 输出：
   - 标准字段摘要
   - 用户选择的字段
   - 原始 Excel 行完整内容
   - Excel 专用 prompt 模板
   - 工作区和范围约束

## 后端组件

### 配置模型

新增数据结构：

```python
@dataclass(frozen=True)
class ExcelProfile:
    canonical_fields: CanonicalFieldMapping
    prompt_fields: tuple[str, ...]
    prompt_template: str
    branch_summary_fields: tuple[str, ...]
```

`CanonicalFieldMapping` 覆盖当前 `BugRecord` 所需的标准字段：

- `issue_id`
- `source_system`
- `priority`
- `primary_category`
- `secondary_category`
- `requester`
- `request_date`
- `requester_status`
- `assignee`
- `assignee_status`
- `resolved_date`
- `description`
- `remark`
- `remark2`

字段值是 Excel 表头名。字段为空时使用当前默认中文列名作为回退。

### 归一化

新增小型归一化函数：

```python
def bug_record_from_row(row: dict[str, str], mapping: CanonicalFieldMapping) -> BugRecord:
    """Build a BugRecord by reading canonical fields from mapped Excel headers."""
```

`filter_bugs` 负责筛选，`bug_record_from_row` 负责字段映射。这样筛选逻辑和字段归一化可以独立测试。

### AI 适配服务

新增 `bugfix_automation/application/excel_adapter_service.py`：

- `excel_adapter_preview(config)`: 返回样例行、当前配置和默认建议。
- `analyze_excel_adapter(config)`: 调用 AI 生成适配建议。
- `save_excel_adapter(payload)`: 校验并保存用户确认后的配置。

AI 调用使用现有 `config.cli_tool`，超时时间默认 120 秒。失败时返回可读错误，不修改配置。

### Prompt 模板

新增 `prompts/excel_adapter.md`，要求 AI 输出严格 JSON，不输出解释性文字。

输出结构：

```json
{
  "canonical_fields": {
    "issue_id": "序号",
    "description": "问题描述"
  },
  "prompt": {
    "fields": ["问题描述", "备注"],
    "template": "请根据问题描述、备注和截图修复当前工作区内可独立完成的问题。"
  },
  "branch_summary_fields": ["问题描述"],
  "filters": [
    {"field": "对接人状态", "op": "not_in", "values": ["已解决", "已处理"]}
  ],
  "warnings": []
}
```

后端会移除不存在的列、无效操作符和空规则。`description` 识别失败时仍允许预览，但保存时提示用户补齐。

## 前端组件

在审批台“数据源”或“AI 提示词”附近新增入口：

- 按钮：`AI 识别 Excel`
- 状态：识别中、识别失败、待保存、已保存
- 结果编辑区：
  - 标准字段映射
  - 推荐筛选规则
  - 传给 AI 的 Excel 列
  - 分支摘要字段
  - Excel 专用 prompt 模板
  - warnings 列表

已有的 `MultiSelectTags` 可复用为字段选择器。保存后刷新配置和 bug 列表。

## 错误处理

- Excel 未配置或 sheet 不存在：前端显示错误，不调用 AI。
- AI 未返回 JSON：显示原始错误摘要，不保存配置。
- AI 返回不存在的列名：后端丢弃该字段并加入 warning。
- `description` 为空：保存失败，要求用户选择一个描述字段。
- `issue_id` 为空：允许保存，运行时回退到 Excel 行号。
- prompt 模板为空：允许保存，使用全局默认模板。
- 筛选规则为空：允许保存，用户可手动补规则；列表可能显示更多行。

## 测试策略

- 配置解析测试：读取 `excel_profile`，缺失时使用默认映射。
- 归一化测试：自定义表头如 `编号`、`标题`、`详情` 能映射成 `BugRecord`。
- Prompt 测试：标准字段和原始 Excel 行同时进入提示词。
- AI 结果校验测试：不存在列、无效 op、空 description 的处理。
- API 测试：adapter preview、analyze 失败、save 成功。
- 前端基础类型测试：配置 payload 包含 `excel_profile`，保存后状态刷新。

## 迁移与兼容

现有 `config.yaml` 不需要立即修改。没有 `excel_profile` 时：

- `BugRecord` 继续读取当前中文默认列名。
- `prompt.fields`、`prompt.template`、`branch_summary_fields` 继续生效。
- 审批台原有筛选规则编辑器继续使用原始 Excel 表头。

当用户保存 AI 识别结果后：

- `excel_profile.canonical_fields` 决定标准字段映射。
- `excel_profile.prompt.fields` 可同步写入现有 `prompt.fields`，让旧 UI 继续展示一致结果。
- `excel_profile.prompt.template` 可同步写入现有 `prompt.template`，避免两套 prompt 配置混淆。
- `excel_profile.prompt.branch_summary_fields` 可同步写入现有 `branch_summary_fields`。

第一版采用同步写入，减少配置入口数量。

## 安全与可复现性

AI 生成的内容不会直接启动修复任务。用户必须保存后，后续运行才使用该配置。

每次运行的配置快照已经写入 `config_snapshots`，新增的 `excel_profile` 会自然进入快照。AI 生成 prompt 的最终结果也会继续写入 `logs/ai/*/prompt.txt`，便于回查。

## 验收标准

- 上传一份列名不同但内容相近的 Excel 后，可以通过 `AI 识别 Excel` 生成字段映射和专用 prompt。
- 用户保存配置后，bug 列表能显示正确的序号、描述、分类、状态和备注。
- 预览 prompt 时能看到标准字段、选中字段、原始 Excel 行和 Excel 专用 prompt。
- 没有 `excel_profile` 的现有配置仍通过当前测试。
- AI 识别失败不会改写 `config.yaml`。
