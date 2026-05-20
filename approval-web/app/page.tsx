"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  BadgeCheck,
  BotMessageSquare,
  CircleDashed,
  CloudUpload,
  Cpu,
  FileCog,
  FileSliders,
  FolderDot,
  FolderSync,
  GitMerge,
  Loader2,
  PackageCheck,
  Pencil,
  RefreshCcwDot,
  RotateCcwKey,
  Save,
  Settings2,
  Sparkles,
  X,
  Zap
} from "lucide-react";
import Link from "next/link";
import { Tooltip } from "antd";
import { Badge } from "../src/components/ui/Badge";
import { MultiSelectTags } from "../src/components/ui/MultiSelectTags";
import { Panel } from "../src/components/ui/Panel";
import { AiChatPanel } from "../src/features/approval/components/AiChatPanel";
import { BranchButton } from "../src/features/approval/components/BranchButton";
import { BugTable } from "../src/features/approval/components/BugTable";
import { DiffView } from "../src/features/approval/components/DiffView";
import { FilterRulesEditor } from "../src/features/approval/components/FilterRulesEditor";
import { FixValidationCard } from "../src/features/approval/components/FixValidationCard";
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

export default function ApprovalPage() {
  const {
    actionDisabled,
    branchSummaryFields,
    bugs,
    busyAction,
    cliTool,
    commitLocation,
    config,
    deleteBug,
    excelFile,
    excelPathInput,
    fixValidation,
    installSchedule,
    loading,
    logPayload,
    maxConcurrency,
    payload,
    postAction,
    postFixValidationAction,
    promptContextPaths,
    promptFields,
    promptTemplate,
    refresh,
    runBug,
    saveAutomationConfig,
    switchWorkspace,
    scheduler,
    schedulerHour,
    schedulerMinute,
    selectExcelPath,
    selected,
    selectedWorkspace,
    setBranchSummaryFields,
    setCliTool,
    setCommitLocation,
    setExcelFile,
    setExcelPathInput,
    setMaxConcurrency,
    setPromptContextPaths,
    setPromptFields,
    setPromptTemplate,
    setSchedulerHour,
    setSchedulerMinute,
    setSelectedBranch,
    toast,
    uploadExcel,
    verifyCommands,
    setVerifyCommands,
    verifyLog
  } = useApprovalDashboard();

  const [previewBug, setPreviewBug] = useState<BugItem | null>(null);
  const [configExpanded, setConfigExpanded] = useState(false);
  const [showWorkspaceManager, setShowWorkspaceManager] = useState(false);
  const [mainTab, setMainTab] = useState<"pending" | "running" | "done" | "integration">("pending");
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
            <select
              className="workspaceSelect"
              value={config?.active_workspace ?? ""}
              onChange={event => void switchWorkspace(event.target.value)}
              disabled={busyAction === "switch-workspace"}
            >
              {(config?.workspaces ?? []).map(workspace => <option key={workspace.id} value={workspace.id}>{workspace.name}</option>)}
            </select>
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

        {/* ── 折叠配置区 ── */}
        {configExpanded ? (
          <section className="configPanel">
            {/* Section 1: 数据源 & 执行 */}
            <div className="configSection">
              <h4 className="configSectionTitle"><FileCog size={14} />数据源</h4>
              <div className="configSectionBody">
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
                      onChange={event => setExcelFile(event.target.files?.[0] ?? null)}
                    />
                    <label className="buttonSmall ghost" htmlFor="excelUploadInput"><CloudUpload size={13} />上传新文件</label>
                    {excelFile ? (
                      <button className="buttonSmall secondary" disabled={Boolean(busyAction)} onClick={() => void uploadExcel()}>
                        {busyAction === "/api/excel/upload" ? <Loader2 size={13} className="spin" /> : <CloudUpload size={13} />}
                        确认上传
                      </button>
                    ) : null}
                  </div>
                  <div className="configFileRow">
                    <input className="configInput" value={excelPathInput} onChange={event => setExcelPathInput(event.target.value)} placeholder="或输入本机 .xlsx 路径" />
                    <button className="buttonSmall ghost" disabled={Boolean(busyAction)} onClick={() => void selectExcelPath()}>使用此路径</button>
                  </div>
                </div>
              </div>
            </div>

            {/* Section 2: 执行设置 */}
            <div className="configSection">
              <h4 className="configSectionTitle"><Cpu size={14} />执行设置</h4>
              <div className="configSectionBody configSectionCols">
                <div className="configField">
                  <label className="configLabel">AI 修复工具</label>
                  <div className="configCliRow">
                    <select className="configSelect" value={["codex", "claude"].includes(cliTool) ? cliTool : "__custom__"} onChange={event => { const v = event.target.value; setCliTool(v === "__custom__" ? "" : v); }}>
                      <option value="codex">OpenAI Codex</option>
                      <option value="claude">Anthropic Claude</option>
                      <option value="__custom__">自定义 CLI</option>
                    </select>
                    <button className="btnSmall" disabled={cliTesting} onClick={async () => {
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
                    <span className="configHint">选择用于修复 Bug 的本地 AI CLI 工具</span>
                  )}
                </div>
                <div className="configField">
                  <label className="configLabel">定时自动修复</label>
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
                </div>
                <div className="configField">
                  <label className="configLabel">同时修复数量</label>
                  <input className="configInput short" value={maxConcurrency} onChange={event => setMaxConcurrency(event.target.value)} inputMode="numeric" />
                  <span className="configHint">最多同时跑几个 Bug（1-8）</span>
                </div>
                <div className="configField">
                  <label className="configLabel">手动执行</label>
                  <button className="buttonSmall secondary" disabled={Boolean(busyAction)} onClick={() => void postAction("/api/run-once", {}, "已开始手动执行")}>
                    {busyAction === "/api/run-once" ? <Loader2 size={13} className="spin" /> : <Sparkles size={13} />}
                    立即执行一轮
                  </button>
                </div>
              </div>
            </div>

            {/* Section 3: AI 提示词设置 */}
            <div className="configSection">
              <h4 className="configSectionTitle"><BotMessageSquare size={14} />AI 提示词</h4>
              <div className="configSectionBody">
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
            </div>

            {/* Section 4: 筛选规则 */}
            <div className="configSection">
              <h4 className="configSectionTitle"><FileSliders size={14} />筛选规则</h4>
              <div className="configSectionBody">
                <div className="ruleList">
                  {(config?.filters ?? []).map(rule => (
                    <div className="ruleItem" key={`${rule.field}-${rule.op}`}>
                      <strong>{rule.field}</strong>
                      <span>{OP_LABELS[rule.op] ?? rule.op}</span>
                      <code>{(rule.values?.length ? rule.values : [rule.value]).filter(Boolean).join(", ") || "空"}</code>
                    </div>
                  ))}
                  {(config?.filters ?? []).length === 0 && <p className="emptyText filterEmpty">暂无筛选规则</p>}
                </div>
                <div className="configSaveRow">
                  <button className="button secondary" onClick={() => setEditingFilters(true)}><Pencil size={14} />编辑筛选规则</button>
                </div>
              </div>
            </div>
          </section>
        ) : null}

        {/* ── 无工作区警告 ── */}
        {config && config.workspaces.length === 0 ? (
          <div className="noWorkspaceBanner">
            <span>⚠️ 当前没有配置任何工作区，无法执行修复。</span>
            <button className="button" onClick={() => setShowWorkspaceManager(true)}>+ 配置工作区</button>
          </div>
        ) : null}

        {/* ── 修复队列 ── */}
        <section className="queuePanel">
          <div className="queuePanelHeader">
            <nav className="mainTabs" aria-label="修复队列状态">
              <button className={`mainTab ${mainTab === "pending" ? "active" : ""}`} onClick={() => setMainTab("pending")}>
                <PackageCheck size={14} />
                待处理
                <span className="mainTabCount pending">{bugs.length}</span>
              </button>
              <button className={`mainTab ${mainTab === "running" ? "active" : ""}`} onClick={() => setMainTab("running")}>
                <Zap size={14} />
                执行中
                <span className="mainTabCount running">{runningItems.length}</span>
              </button>
              <button className={`mainTab ${mainTab === "done" ? "active" : ""}`} onClick={() => setMainTab("done")}>
                <BadgeCheck size={14} />
                已完成
                <span className="mainTabCount done">{doneItems.length}</span>
              </button>
              <button className={`mainTab ${mainTab === "integration" ? "active" : ""}`} onClick={() => setMainTab("integration")}>
                <GitMerge size={14} />
                集成
              </button>
            </nav>
            <div className="queuePanelSummary">
              {mainTab === "pending" ? `等待处理 ${bugs.length} 个 Excel 命中` : null}
              {mainTab === "running" ? `正在执行 ${runningItems.length} 个修复任务` : null}
              {mainTab === "done" ? `已完成 ${doneItems.length} 个 worktree` : null}
              {mainTab === "integration" ? "进入集成预演页，选择真实 fix/* 分支和目标分支" : null}
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
            {mainTab === "integration" && (
              <div className="tabEmpty integration">
                <GitMerge size={20} />
                <span>集成预演已收敛到独立页面，避免从当前 Excel 列表误判可合并分支。</span>
                <Link className="button primary" href="/integration">打开集成预演</Link>
              </div>
            )}
          </div>
        </section>

        {/* ── 审批区 ── */}
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
                  verifyCommands={verifyCommands}
                  onVerifyCommandsChange={setVerifyCommands}
                  onCommitLocationChange={setCommitLocation}
                  onVerify={() => void postFixValidationAction("verify", "自动合并验证已完成", { verify_commands: verifyCommands.split("\n").filter(Boolean) })}
                  onCommit={() => void postFixValidationAction("commit", "已提交此修复", { location: commitLocation })}
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
                verifyLog={verifyLog}
                disabled={actionDisabled}
                loading={busyAction === "/api/rework"}
                onRework={async (params) => {
                  await postAction("/api/rework", params, "已提交重新修改");
                }}
              />
            </Panel>
          </aside>
        </section>
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
