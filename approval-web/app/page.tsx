"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  BadgeCheck,
  BotMessageSquare,
  CircleDashed,
  ClipboardCheck,
  CloudUpload,
  Code2,
  Cpu,
  FileCog,
  FileSliders,
  FileSpreadsheet,
  FolderDot,
  FolderSync,
  GitBranch,
  History,
  Loader2,
  PackageCheck,
  Pencil,
  RefreshCcwDot,
  RotateCcwKey,
  Save,
  Settings2,
  ShieldCheck,
  Sparkles,
  X,
  Zap
} from "lucide-react";
import { Select, Tooltip } from "antd";
import { Badge } from "../src/components/ui/Badge";
import { MultiSelectTags } from "../src/components/ui/MultiSelectTags";
import { Panel } from "../src/components/ui/Panel";
import { AiChatPanel } from "../src/features/approval/components/AiChatPanel";
import { BranchButton } from "../src/features/approval/components/BranchButton";
import { BugTable } from "../src/features/approval/components/BugTable";
import { DiffView } from "../src/features/approval/components/DiffView";
import { ExcelAdapterPanel } from "../src/features/approval/components/ExcelAdapterPanel";
import { FilterRulesEditor } from "../src/features/approval/components/FilterRulesEditor";
import { FixValidationCard } from "../src/features/approval/components/FixValidationCard";
import { OperationHistoryPanel } from "../src/features/approval/components/OperationHistoryPanel";
import { OnlineSheetPanel } from "../src/features/approval/components/OnlineSheetPanel";
import { PromptPreview } from "../src/features/approval/components/PromptPreview";
import { WorkspaceManager } from "../src/features/approval/components/WorkspaceManager";
import { useApprovalDashboard } from "../src/features/approval/hooks/useApprovalDashboard";
import { compactPath } from "../src/lib/format";
import type { BugItem, FilterRule } from "../src/features/approval/types";

const OP_LABELS: Record<string, string> = {
  equals: "等于",
  not_equals: "不等于",
  in: "包含任一",
  not_in: "不含任一",
  all_in: "全部在内",
  contains: "文本包含",
  not_contains: "文本不含",
};

const WORKFLOW_STEPS = [
  { icon: FileSpreadsheet, label: "清单", detail: "Excel / 在线表格" },
  { icon: PackageCheck, label: "筛选", detail: "命中待处理 Bug" },
  { icon: GitBranch, label: "隔离", detail: "fix/* worktree" },
  { icon: Code2, label: "修复", detail: "AI CLI 执行" },
  { icon: ClipboardCheck, label: "审查", detail: "Diff / 日志 / 验证" },
  { icon: ShieldCheck, label: "合入", detail: "通过 / 拒绝 / 重改" },
];

type ConfigStep = "source" | "prompt" | "filters" | "runtime";

const CONFIG_STEPS: Array<{ key: ConfigStep; icon: typeof FileCog; label: string; detail: string }> = [
  { key: "source", icon: FileSpreadsheet, label: "接入清单", detail: "上传 Excel 或在线表格" },
  { key: "prompt", icon: BotMessageSquare, label: "理解规则", detail: "字段映射、代码范围、修复边界" },
  { key: "filters", icon: FileSliders, label: "入队范围", detail: "筛出本轮要修的 Bug" },
  { key: "runtime", icon: Cpu, label: "执行验证", detail: "测试 AI CLI 后再运行" },
];

export default function ApprovalPage() {
  const {
    actionDisabled,
    analyzeExcelAdapter,
    branchSummaryFields,
    bugs,
    busyAction,
    cliTool,
    commitLocation,
    config,
    deleteBug,
    excelAdapter,
    excelFile,
    fixValidation,
    installSchedule,
    importOnlineSheet,
    loading,
    logPayload,
    maxConcurrency,
    onlineSheetPreview,
    onlineSheetProvider,
    onlineSheetProviders,
    onlineSheetRange,
    onlineSheetUrl,
    payload,
    postAction,
    postFixValidationAction,
    promptContextPaths,
    promptFields,
    promptTemplate,
    refresh,
    previewOnlineSheet,
    runBug,
    saveAutomationConfig,
    saveExcelAdapter,
    switchWorkspace,
    scheduler,
    schedulerHour,
    schedulerMinute,
    selected,
    selectedWorkspace,
    setBranchSummaryFields,
    setCliTool,
    setCommitLocation,
    setExcelAdapter,
    setExcelFile,
    setMaxConcurrency,
    setOnlineSheetProvider,
    setOnlineSheetRange,
    setOnlineSheetUrl,
    setPromptContextPaths,
    setPromptFields,
    setPromptTemplate,
    setSchedulerHour,
    setSchedulerMinute,
    setSelectedBranch,
    toast,
    uploadExcel,
  } = useApprovalDashboard();

  const [previewBug, setPreviewBug] = useState<BugItem | null>(null);
  const [configExpanded, setConfigExpanded] = useState(false);
  const [configStep, setConfigStep] = useState<ConfigStep>("source");
  const [showWorkspaceManager, setShowWorkspaceManager] = useState(false);
  const [mainTab, setMainTab] = useState<"pending" | "running" | "done" | "history">("pending");
  const [cliTestResult, setCliTestResult] = useState<{ ok: boolean; version?: string; error?: string } | null>(null);
  const [cliTesting, setCliTesting] = useState(false);
  const [scrollToFile, setScrollToFile] = useState<string | null>(null);
  const [editingFilters, setEditingFilters] = useState(false);
  const [excelHeaders, setExcelHeaders] = useState<string[]>([]);
  const [inspectorWidth, setInspectorWidth] = useState(420);
  const dragRef = useRef<{ startX: number; startW: number } | null>(null);

  // Load Excel headers for prompt-field picker (refresh when excel file changes)
  useEffect(() => {
    let alive = true;
    fetch("/api/excel/columns")
      .then(r => r.json())
      .then(data => { if (alive && data?.ok) setExcelHeaders(data.headers || []); })
      .catch(() => { /* ignore */ });
    return () => { alive = false; };
  }, [excelFile]);

  // Reset scrollToFile when selected branch changes
  useEffect(() => { setScrollToFile(null); }, [selected?.branch]);

  const handleFileChipClick = (file: string) => {
    setScrollToFile(prev => (prev === file ? `${file}?t=${Date.now()}` : file));
  };

  const handleSaveFilters = async (filters: FilterRule[]) => {
    await fetch("/api/filters/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filters }),
    });
    setEditingFilters(false);
    await refresh();
  };

  const configStepIndex = CONFIG_STEPS.findIndex(step => step.key === configStep);
  const goPrevConfigStep = () => setConfigStep(CONFIG_STEPS[Math.max(0, configStepIndex - 1)].key);
  const goNextConfigStep = () => setConfigStep(CONFIG_STEPS[Math.min(CONFIG_STEPS.length - 1, configStepIndex + 1)].key);

  const handleResizeStart = (e: React.MouseEvent) => {
    dragRef.current = { startX: e.clientX, startW: inspectorWidth };
    const onMove = (ev: MouseEvent) => {
      if (!dragRef.current) return;
      const delta = dragRef.current.startX - ev.clientX;
      setInspectorWidth(Math.max(320, Math.min(700, dragRef.current.startW + delta)));
    };
    const onUp = () => {
      dragRef.current = null;
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  };

  // Derived task lists
  const runningItems = useMemo(() => payload.items.filter(item => item.active), [payload.items]);
  const doneItems = useMemo(() => payload.items.filter(item => !item.active), [payload.items]);

  return (
    <main className="consoleShell">
      <section className="mainStage">
        {/* ── 顶部工作区切换 ── */}
        <header className="commandBar">
          <div className="commandBarLeft">
            <FolderDot size={18} className="commandBarIcon" />
            <Select
              className="workspaceSelect"
              value={config?.active_workspace ?? undefined}
              onChange={value => void switchWorkspace(value)}
              disabled={busyAction === "switch-workspace"}
              variant="outlined"
              popupMatchSelectWidth={false}
              options={(config?.workspaces ?? []).map(workspace => ({ value: workspace.id, label: workspace.name }))}
            />
            {selectedWorkspace?.scope ? <span className={`wsScopeBadge ${selectedWorkspace.scope}`}>{selectedWorkspace.scope === "frontend" ? "前端" : selectedWorkspace.scope === "backend" ? "后端" : "全栈"}</span> : null}
            <span className="commandBarPath">{config?.target_repo}/{config?.target_app_path}</span>
          </div>
          <div className="commandActions">
            <button className="button ghost" onClick={() => void refresh()} disabled={loading} title="刷新数据">
              <RefreshCcwDot size={16} className={loading ? "spin" : ""} />
            </button>
            <button className="button ghost" onClick={() => setShowWorkspaceManager(true)} title="管理工作区">
              <FolderSync size={16} />
            </button>
            <button className="button ghost" onClick={() => setConfigExpanded(!configExpanded)} title="设置">
              <Settings2 size={16} />
            </button>
          </div>
        </header>

        {toast ? <div className="toast">{toast}</div> : null}

        {/* ── 无工作区警告 ── */}
        {config && config.workspaces.length === 0 ? (
          <div className="noWorkspaceBanner">
            <span>⚠️ 当前没有配置任何工作区，无法执行修复。</span>
            <button className="button" onClick={() => setShowWorkspaceManager(true)}>+ 配置工作区</button>
          </div>
        ) : null}

        <section className="workflowStrip" aria-label="从 Bug 清单到可审批修复的工作流">
          {WORKFLOW_STEPS.map((step, index) => {
            const StepIcon = step.icon;
            return (
              <div className="workflowStep" key={step.label}>
                <span className="workflowIndex">{index + 1}</span>
                <StepIcon size={16} />
                <strong>{step.label}</strong>
                <small>{step.detail}</small>
              </div>
            );
          })}
        </section>

        <section className={`workbenchGrid ${mainTab === "history" ? "historyMode" : ""}`}>
          {/* ── 修复队列 ── */}
          <aside className="queuePanel">
            <div className="queuePanelHeader">
              <div className="queuePanelTitle">
                <strong>修复队列</strong>
                <span>{mainTab === "pending" ? `${bugs.length} 个 Excel 命中` : mainTab === "running" ? `${runningItems.length} 个运行中` : mainTab === "done" ? `${doneItems.length} 个结果` : "操作记录"}</span>
              </div>
              <nav className="mainTabs" aria-label="修复队列状态">
                <button className={`mainTab ${mainTab === "pending" ? "active" : ""}`} onClick={() => setMainTab("pending")} title="待处理">
                  <PackageCheck size={14} />
                  <span className="mainTabLabel">待处理</span>
                  <span className="mainTabCount pending">{bugs.length}</span>
                </button>
                <button className={`mainTab ${mainTab === "running" ? "active" : ""}`} onClick={() => setMainTab("running")} title="执行中">
                  <Zap size={14} />
                  <span className="mainTabLabel">执行中</span>
                  <span className="mainTabCount running">{runningItems.length}</span>
                </button>
                <button className={`mainTab ${mainTab === "done" ? "active" : ""}`} onClick={() => setMainTab("done")} title="已完成">
                  <BadgeCheck size={14} />
                  <span className="mainTabLabel">已完成</span>
                  <span className="mainTabCount done">{doneItems.length}</span>
                </button>
                <button className={`mainTab ${mainTab === "history" ? "active" : ""}`} onClick={() => setMainTab("history")} title="记录">
                  <History size={14} />
                  <span className="mainTabLabel">记录</span>
                </button>
              </nav>
            </div>
            <div className="queueFilterBar">
              <div className="queueFilterIntro">
                <FileSliders size={14} />
                <span>入队筛选</span>
                <strong>{(config?.filters ?? []).length} 条</strong>
              </div>
              <div className="queueFilterChips" aria-label="当前入队规则">
                {(config?.filters ?? []).length > 0 ? (config?.filters ?? []).map(rule => (
                  <span className="queueFilterChip" key={`${rule.field}-${rule.op}-${rule.value}-${(rule.values || []).join(",")}`}>
                    <strong>{rule.field}</strong>
                    <em>{OP_LABELS[rule.op] ?? rule.op}</em>
                    <code>{(rule.values?.length ? rule.values : [rule.value]).filter(Boolean).join(", ") || "空"}</code>
                  </span>
                )) : (
                  <span className="queueFilterEmpty">暂无规则，点击右侧按钮设置入队范围</span>
                )}
              </div>
              <button className="buttonSmall ghost" onClick={() => setEditingFilters(true)} title="编辑入队规则">
                <Pencil size={13} />
                编辑
              </button>
            </div>
            <div className="queueFilterResults">
              <span className="queueFilterResultLabel">筛选结果</span>
              <strong>{bugs.length} 条</strong>
              <div className="queueFilterResultList" aria-label="筛选命中的 Bug">
                {bugs.length > 0 ? bugs.map(bug => (
                  <button
                    key={`filter-result-${bug.issue_id}-${bug.excel_row}`}
                    className="queueFilterResultChip"
                    onClick={() => setMainTab("pending")}
                    title={bug.description || `Excel 行 ${bug.excel_row}`}
                  >
                    <span>#{bug.issue_id || bug.excel_row}</span>
                    <em>{bug.description || bug.primary_category || "未填写问题描述"}</em>
                  </button>
                )) : (
                  <span className="queueFilterEmpty">没有命中任何 Bug，请调整入队规则</span>
                )}
              </div>
            </div>
            <div className="mainTabContent">
              {mainTab === "pending" && (
                <BugTable bugs={bugs} busyAction={busyAction} noWorkspace={!config || config.workspaces.length === 0} onRun={runBug} onDelete={deleteBug} onPreview={setPreviewBug} />
              )}
              {mainTab === "running" && (
                runningItems.length === 0
                  ? <div className="tabEmpty running"><Zap size={20} /><span>暂无正在执行的任务</span></div>
                  : <div className="branchGrid">{runningItems.map(item => (
                      <BranchButton key={item.branch} item={item} active={item.branch === selected?.branch} validationStatus={item.branch === selected?.branch ? fixValidation?.status : undefined} onClick={() => setSelectedBranch(item.branch)} />
                    ))}</div>
              )}
              {mainTab === "done" && (
                doneItems.length === 0
                  ? <div className="tabEmpty done"><BadgeCheck size={20} /><span>暂无已完成的任务</span></div>
                  : <div className="branchGrid">{doneItems.map(item => (
                      <BranchButton key={item.branch} item={item} active={item.branch === selected?.branch} validationStatus={item.branch === selected?.branch ? fixValidation?.status : undefined} onClick={() => setSelectedBranch(item.branch)} />
                    ))}</div>
              )}
              {mainTab === "history" && (
                <OperationHistoryPanel />
              )}
            </div>
          </aside>

          {/* ── 审批区 ── */}
          {mainTab !== "history" ? (
          <section className="reviewGrid" style={{ gridTemplateColumns: `minmax(0, 1fr) 10px ${inspectorWidth}px` }}>
            <div className="reviewMain">
              {selected ? (
                <div className="reviewMainInner">
                  <div className="approvalBar">
                    <div className="reviewMeta">
                      <span className="approvalBranch"><FileCog size={13} />{selected.branch}</span>
                      <span className="reviewFileCount">{selected.changed_files.length} 个改动文件</span>
                      {selected.active ? <span className="reviewRunState running">执行中</span> : selected.pending ? <span className="reviewRunState pending">待验证</span> : <span className="reviewRunState clean">已清理</span>}
                    </div>
                  </div>
                  <FixValidationCard
                    item={selected}
                    validation={fixValidation}
                    busyAction={busyAction}
                    actionDisabled={actionDisabled}
                    commitLocation={commitLocation}
                    onCommitLocationChange={setCommitLocation}
                    onVerify={() => void postFixValidationAction("verify", "提交预演已生成")}
                    onCommit={() => void postFixValidationAction("commit", "已提交此修复", { location: commitLocation })}
                    onMergeToTarget={() => void postFixValidationAction("merge-to-target", "已合并到目标分支")}
                    onRevert={() => void postFixValidationAction("revert", "已撤回此提交")}
                    onUndoCommit={() => void postFixValidationAction("undo-commit", "已撤销上次提交")}
                    onRemovePreview={() => void postFixValidationAction("remove-preview", "已移除此预演")}
                    onReject={() => void postAction("/api/reject", { branch: selected.branch }, "已拒绝并删除分支")}
                    onCleanup={() => void postFixValidationAction("cleanup-source", "已清理来源分支")}
                  />
                  <DiffView diff={selected.diff} scrollToFile={scrollToFile} changedFiles={selected.changed_files} branch={selected.branch} />
                </div>
              ) : (
                <div className="blankState">
                  <CircleDashed size={32} />
                  <h2>没有待处理的修复</h2>
                  <p>点击 Bug 列表中的「预览」查看提示词，或「执行」开始修复。</p>
                </div>
              )}
            </div>

            {/* resize handle */}
            <div className="resizeHandle" onMouseDown={handleResizeStart} />

            <aside className="inspector">
              <Panel title="AI 对话" icon={<BotMessageSquare size={16} />} aside={compactPath(logPayload.path)}>
                <AiChatPanel
                  item={selected ?? null}
                  logPayload={logPayload}
                  disabled={actionDisabled}
                  loading={busyAction === "/api/rework"}
                  onRework={async (params) => {
                    await postAction("/api/rework", params, "已提交重新修改");
                  }}
                />
              </Panel>
            </aside>
          </section>
          ) : null}
        </section>
        <footer className="statusBar">
          <span>{selectedWorkspace?.name || "未选择工作区"} · {compactPath(config?.target_app_path || "") || "未配置目录"}</span>
          <span>{cliTool || "codex"} · 待处理 {bugs.length} · 执行中 {runningItems.length} · 结果 {doneItems.length}</span>
        </footer>
      </section>

      {/* ── 提示词预览弹窗 ── */}
      {previewBug ? (
        <PromptPreview
          bug={previewBug}
          onClose={() => setPreviewBug(null)}
          onRunWithPrompt={(bug) => { setPreviewBug(null); void runBug(bug); }}
        />
      ) : null}

      {/* ── 筛选规则编辑弹窗 ── */}
      {editingFilters ? (
        <div className="promptOverlay" onClick={() => setEditingFilters(false)}>
          <div className="filterEditorModal" onClick={e => e.stopPropagation()}>
            <header className="promptModalHeader">
              <div className="promptModalTitle">
                <FileSliders size={16} />
                <h3>筛选规则</h3>
              </div>
              <button className="promptModalClose" onClick={() => setEditingFilters(false)} title="关闭"><X size={18} /></button>
            </header>
            <div className="filterEditorModalBody">
              <FilterRulesEditor
                rules={config?.filters ?? []}
                onSave={async (rules) => { await handleSaveFilters(rules); setEditingFilters(false); }}
                onCancel={() => setEditingFilters(false)}
              />
            </div>
          </div>
        </div>
      ) : null}

      {/* ── 配置向导弹窗 ── */}
      {configExpanded ? (
        <div className="promptOverlay" onClick={() => setConfigExpanded(false)}>
          <section className="configPanel configModal" onClick={event => event.stopPropagation()}>
            <div className="configGuideHeader">
              <div className="configGuideIntro">
                <strong>配置向导</strong>
                <span>按“清单接入 → AI 理解 → 入队范围 → 执行验证”完成配置，最后再测试 Codex/Claude 是否可用。</span>
              </div>
              <button className="promptModalClose" onClick={() => setConfigExpanded(false)} title="关闭"><X size={18} /></button>
            </div>
            <nav className="configStepNav" aria-label="配置步骤">
              {CONFIG_STEPS.map((step, index) => {
                const StepIcon = step.icon;
                const active = step.key === configStep;
                const done = index < configStepIndex;
                return (
                  <button
                    key={step.key}
                    className={`configStepButton ${active ? "active" : ""} ${done ? "done" : ""}`}
                    onClick={() => setConfigStep(step.key)}
                  >
                    <span className="configStepNumber">{index + 1}</span>
                    <StepIcon size={15} />
                    <span className="configStepCopy">
                      <strong>{step.label}</strong>
                      <small>{step.detail}</small>
                    </span>
                  </button>
                );
              })}
            </nav>
            <div className="configModalBody">
              {configStep === "source" ? <div className="configSection">
                <h4 className="configSectionTitle"><FileSpreadsheet size={14} />接入清单</h4>
                <div className="configSectionBody">
                  <div className="configLearningNote">
                    <strong>第 1 步：先告诉系统 Bug 从哪里来。</strong>
                    <span>推荐先用本地 Excel 跑通；团队协作时再接入在线表格。字段名不同也没关系，下一步会读取表头并生成映射建议。</span>
                  </div>
                  <div className="configField">
                    <label className="configLabel">Bug 清单文件</label>
                    <div className="configFileRow">
                      <code className="configFilePath">{compactPath(config?.excel_path) || "未选择"}</code>
                      <input
                        id="excelUploadInput"
                        className="fileInput"
                        type="file"
                        accept=".xlsx"
                        onClick={event => { event.currentTarget.value = ""; }}
                        onChange={event => { const f = event.target.files?.[0]; if (f) { setExcelFile(f); void uploadExcel(f); } }}
                      />
                      <label className="buttonSmall ghost" htmlFor="excelUploadInput">
                        {busyAction === "/api/excel/upload" ? <Loader2 size={13} className="spin" /> : <CloudUpload size={13} />}
                        上传文件
                      </label>
                    </div>
                  </div>
                  <OnlineSheetPanel
                    providers={onlineSheetProviders}
                    provider={onlineSheetProvider}
                    url={onlineSheetUrl}
                    range={onlineSheetRange}
                    preview={onlineSheetPreview}
                    busyAction={busyAction}
                    onProviderChange={setOnlineSheetProvider}
                    onUrlChange={setOnlineSheetUrl}
                    onRangeChange={setOnlineSheetRange}
                    onPreview={previewOnlineSheet}
                    onImport={importOnlineSheet}
                  />
                </div>
              </div> : null}

              {configStep === "runtime" ? <div className="configSection">
                <h4 className="configSectionTitle"><Cpu size={14} />执行验证</h4>
                <div className="configSectionBody configRuntimeBody">
                  <div className="configLearningNote wide">
                    <strong>第 4 步：最后确认本地 AI CLI 能完成修复。</strong>
                    <span>前 3 步决定“修什么、怎么读、哪些入队”，这里才测试 Codex/Claude 是否可用。并发建议先保持 1，流程稳定后再提高；定时执行属于高级用法，可以先不启用。</span>
                  </div>
                  <div className="configField runtimeToolPanel">
                    <label className="configLabel">1. 测试 AI 修复工具</label>
                    <div className="configCliRow">
                      <select className="configSelect" value={["codex", "claude"].includes(cliTool) ? cliTool : "__custom__"} onChange={event => { const v = event.target.value; setCliTool(v === "__custom__" ? "" : v); }}>
                        <option value="codex">OpenAI Codex</option>
                        <option value="claude">Anthropic Claude</option>
                        <option value="__custom__">自定义 CLI</option>
                      </select>
                      <button className="buttonSmall ghost cliTestButton" disabled={cliTesting} onClick={async () => {
                        setCliTesting(true); setCliTestResult(null);
                        try {
                          const res = await fetch("/api/cli/test", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ cli_tool: cliTool || "codex" }) });
                          setCliTestResult(await res.json());
                        } catch { setCliTestResult({ ok: false, error: "请求失败" }); }
                        setCliTesting(false);
                      }}>{cliTesting ? "测试中…" : "测试连接"}</button>
                      {!["codex", "claude"].includes(cliTool) ? (
                        <input className="configInput" value={cliTool} onChange={event => setCliTool(event.target.value)} placeholder="自定义 CLI 命令路径" />
                      ) : null}
                    </div>
                    {cliTestResult ? (
                      <span className={`configHint ${cliTestResult.ok ? "hintSuccess" : "hintError"}`}>
                        {cliTestResult.ok ? `✓ ${cliTestResult.version}` : `✗ ${cliTestResult.error}`}
                      </span>
                    ) : (
                      <span className="configHint">选择本机用于修改代码的 CLI，然后点击测试连接</span>
                    )}
                    {config?.capability_status ? (
                      <span className="configHint">
                        能力包：{config.capability_status.provider}
                        {config.capability_status.source ? ` · ${config.capability_status.source}` : ""}
                        {config.capability_status.warnings.length > 0
                          ? ` · ${config.capability_status.warnings.length} 个提示`
                          : " · 已检测"}
                      </span>
                    ) : null}
                  </div>
                  <div className="runtimeActionPanel">
                    <div className="configField">
                      <label className="configLabel">2. 同时修复数量</label>
                      <input className="configInput short runtimeNumberInput" value={maxConcurrency} onChange={event => setMaxConcurrency(event.target.value)} inputMode="numeric" />
                      <span className="configHint">建议先用 1，稳定后再提高到 2-8</span>
                    </div>
                    <div className="configField">
                      <label className="configLabel">3. 手动执行一轮</label>
                      <button className="buttonSmall secondary runtimeRunButton" disabled={Boolean(busyAction)} onClick={() => void postAction("/api/run-once", {}, "已开始手动执行")}>
                        {busyAction === "/api/run-once" ? <Loader2 size={13} className="spin" /> : <Sparkles size={13} />}
                        立即执行一轮
                      </button>
                      <span className="configHint">会按左侧队列和并发数开始修复</span>
                    </div>
                  </div>
                  <div className="configField runtimeSchedulePanel">
                    <label className="configLabel">4. 可选：定时自动修复</label>
                    <div className="configScheduleRow">
                      <Badge tone={scheduler?.loaded ? "green" : "gray"}>{scheduler?.loaded ? "运行中" : "未启用"}</Badge>
                      <span className="configScheduleTime">
                        每天
                        <input className="configTimeInput" value={schedulerHour} onChange={event => setSchedulerHour(event.target.value)} inputMode="numeric" />
                        :
                        <input className="configTimeInput" value={schedulerMinute} onChange={event => setSchedulerMinute(event.target.value)} inputMode="numeric" />
                      </span>
                      <button className="buttonSmall ghost" disabled={Boolean(busyAction)} onClick={installSchedule}><Save size={13} />保存</button>
                      {scheduler?.installed ? <button className="buttonSmall ghost" disabled={Boolean(busyAction)} onClick={() => void postAction("/api/scheduler/uninstall", {}, "定时任务已取消")} title="取消定时"><RotateCcwKey size={13} /></button> : null}
                    </div>
                    <span className="configHint">定时执行适合团队流程稳定后开启，前期可以保持未启用</span>
                  </div>
                </div>
              </div> : null}

              {configStep === "prompt" ? <div className="configSection">
                <h4 className="configSectionTitle"><BotMessageSquare size={14} />理解规则</h4>
                <div className="configSectionBody">
                  <div className="configLearningNote">
                    <strong>第 2 步：让 AI 读懂你的清单和代码边界。</strong>
                    <span>先用“智能识别 Excel”生成字段映射，再选择要传给 AI 的列和重点代码目录。字段越准确，AI 越容易理解问题；路径越聚焦，修复越可控。</span>
                  </div>
                  <ExcelAdapterPanel
                    adapter={excelAdapter}
                    busyAction={busyAction}
                    onAnalyze={analyzeExcelAdapter}
                    onSave={saveExcelAdapter}
                    onClear={() => setExcelAdapter(null)}
                  />
                  <div className="configFieldRow">
                    <div className="configField">
                      <label className="configLabel">传给 AI 的 Excel 列</label>
                      <MultiSelectTags
                        value={(promptFields || "").split("\n").map(s => s.trim()).filter(Boolean)}
                        options={excelHeaders.map(h => ({ value: h, label: h }))}
                        onChange={(next) => setPromptFields(next.join("\n"))}
                        placeholder={excelHeaders.length ? "选择要传给 AI 的列" : "请先上传 Excel 后选择列"}
                        allowCustom
                      />
                      <span className="configHint">选择后，AI 会读取这些列的数据。选项自动来自当前 Excel 表头</span>
                    </div>
                    <div className="configField">
                      <label className="configLabel">AI 优先阅读的代码路径</label>
                      <textarea className="configTextarea" value={promptContextPaths} onChange={event => setPromptContextPaths(event.target.value)} rows={3} placeholder={"src/app\nsrc/components\nsrc/services"} />
                      <span className="configHint">每行一个路径，AI 会先看这些目录的代码</span>
                    </div>
                  </div>
                  <div className="configField">
                    <label className="configLabel">补充修复指引</label>
                    <textarea className="configTextarea" value={promptTemplate} onChange={event => setPromptTemplate(event.target.value)} rows={3} placeholder="额外的修复规则和约束，会追加到每个 Bug 的提示词末尾" />
                    <span className="configHint">例：只修改前端代码，不要修改后端接口；修复后运行 lint 验证</span>
                  </div>
                  <div className="configSaveRow">
                    <button className="button secondary" onClick={saveAutomationConfig} disabled={Boolean(busyAction)}><Save size={14} />保存配置</button>
                  </div>
                </div>
              </div> : null}

              {configStep === "filters" ? <div className="configSection">
                <h4 className="configSectionTitle"><FileSliders size={14} />入队范围</h4>
                <div className="configSectionBody">
                  <div className="configLearningNote">
                    <strong>第 3 步：入队范围已前置到修复队列顶部。</strong>
                    <span>这里保留说明和跳转入口，实际编辑建议直接在左侧队列上方完成，这样更符合“先看队列、再收窄范围”的使用路径。</span>
                  </div>
                  <div className="configSaveRow">
                    <button className="button secondary" onClick={() => { setConfigExpanded(false); setEditingFilters(true); }}><Pencil size={14} />打开队列筛选</button>
                  </div>
                </div>
              </div> : null}
            </div>
            <div className="configGuideFooter">
              <button className="buttonSmall ghost" onClick={goPrevConfigStep} disabled={configStepIndex === 0}>上一步</button>
              <span>第 {configStepIndex + 1} / {CONFIG_STEPS.length} 步</span>
              {configStepIndex < CONFIG_STEPS.length - 1 ? (
                <button className="buttonSmall secondary" onClick={goNextConfigStep}>下一步</button>
              ) : (
                <button className="buttonSmall secondary" onClick={saveAutomationConfig} disabled={Boolean(busyAction)}><Save size={13} />保存并完成</button>
              )}
            </div>
          </section>
        </div>
      ) : null}

      {/* ── 工作区管理弹窗 ── */}
      {showWorkspaceManager ? (
        <WorkspaceManager
          workspaces={config?.workspaces ?? []}
          activeWorkspace={config?.active_workspace ?? ""}
          onClose={() => setShowWorkspaceManager(false)}
          onRefresh={() => { setShowWorkspaceManager(false); void refresh(); }}
        />
      ) : null}
    </main>
  );
}
