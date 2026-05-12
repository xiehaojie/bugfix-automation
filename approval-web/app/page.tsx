"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  CheckCircle2,
  Clock3,
  Code2,
  Database,
  FileText,
  GitBranch,
  ImagePlus,
  Loader2,
  MessageSquareText,
  PlayCircle,
  Power,
  RefreshCw,
  RotateCcw,
  Save,
  Settings2,
  TerminalSquare,
  Timer,
  Trash2,
  Upload,
  XCircle
} from "lucide-react";

type FixItem = {
  branch: string;
  path: string;
  changed_files: string[];
  pending: boolean;
  active: boolean;
  task_status: string;
  task_phase: string;
  task_detail: string;
  task_updated_at: string;
  status: string;
  diff: string;
  log_path?: string;
};

type DashboardPayload = {
  pending_count: number;
  items: FixItem[];
};

type BugItem = {
  issue_id: string;
  excel_row: number;
  branch: string;
  source_system: string;
  primary_category: string;
  secondary_category: string;
  requester_status: string;
  assignee_status: string;
  description: string;
  remark: string;
  remark2: string;
  active: boolean;
  task_status: string;
  task_phase: string;
  task_detail: string;
  task_updated_at: string;
  images: Array<{ path: string; name: string; url: string }>;
};

type Workspace = {
  id: string;
  name: string;
  target_repo: string;
  target_app_path: string;
  verify_commands: string[];
  max_concurrency: number;
};

type FilterRule = {
  field: string;
  op: string;
  value: string;
  values: string[];
};

type ConfigPayload = {
  target_repo: string;
  target_app_path: string;
  excel_path: string;
  excel_file: {
    path?: string;
    original_name?: string;
    stored_name?: string;
    size?: number;
    mtime?: string;
    sha256?: string;
  };
  assignee: string;
  api_port: number;
  active_workspace: string;
  max_concurrency: number;
  workspaces: Workspace[];
  filters: FilterRule[];
  branch_summary_fields: string[];
  prompt: {
    fields: string[];
    template: string;
    context_paths: string[];
  };
};

type SchedulerPayload = {
  label: string;
  plist_path: string;
  installed: boolean;
  loaded: boolean;
  schedule_hour: number;
  schedule_minute: number;
};

type LogPayload = {
  branch: string;
  path: string;
  content: string;
};

type TaskLike = {
  active: boolean;
  pending?: boolean;
  task_status: string;
  task_phase: string;
  task_detail: string;
};

const splitLines = (value: string) =>
  value
    .split("\n")
    .map(line => line.trim())
    .filter(Boolean);

export default function ApprovalPage() {
  const [payload, setPayload] = useState<DashboardPayload>({ pending_count: 0, items: [] });
  const [bugs, setBugs] = useState<BugItem[]>([]);
  const [scheduler, setScheduler] = useState<SchedulerPayload | null>(null);
  const [config, setConfig] = useState<ConfigPayload | null>(null);
  const [selectedBranch, setSelectedBranch] = useState("");
  const [loading, setLoading] = useState(true);
  const [busyAction, setBusyAction] = useState("");
  const [toast, setToast] = useState("");
  const [note, setNote] = useState("");
  const [filePaths, setFilePaths] = useState("");
  const [imagePaths, setImagePaths] = useState("");
  const [schedulerHour, setSchedulerHour] = useState("22");
  const [schedulerMinute, setSchedulerMinute] = useState("0");
  const [excelFile, setExcelFile] = useState<File | null>(null);
  const [excelPathInput, setExcelPathInput] = useState("/Users/xiehaojie/Desktop/亦城数智人在线清单.xlsx");
  const [logPayload, setLogPayload] = useState<LogPayload>({ branch: "", path: "", content: "" });
  const [promptFields, setPromptFields] = useState("");
  const [promptContextPaths, setPromptContextPaths] = useState("");
  const [promptTemplate, setPromptTemplate] = useState("");
  const [maxConcurrency, setMaxConcurrency] = useState("2");
  const [branchSummaryFields, setBranchSummaryFields] = useState("");
  const logPaneRef = useRef<HTMLPreElement | null>(null);

  const selected = useMemo(
    () => payload.items.find(item => item.branch === selectedBranch) ?? payload.items[0],
    [payload.items, selectedBranch]
  );
  const pendingItems = payload.items.filter(item => item.pending);
  const cleanItems = payload.items.filter(item => !item.pending);
  const selectedWorkspace = config?.workspaces.find(workspace => workspace.id === config.active_workspace);
  const actionDisabled = Boolean(busyAction) || !selected;

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [nextPayload, nextBugsPayload, nextConfig, nextScheduler] = await Promise.all([
        fetchJson<DashboardPayload>("/api/items"),
        fetchJson<{ bugs: BugItem[] }>("/api/bugs"),
        fetchJson<ConfigPayload>("/api/config"),
        fetchJson<SchedulerPayload>("/api/scheduler")
      ]);
      setPayload(nextPayload);
      setBugs(nextBugsPayload.bugs ?? []);
      setConfig(nextConfig);
      setScheduler(nextScheduler);
      setSelectedBranch(current => {
        if (current && nextPayload.items.some(item => item.branch === current)) return current;
        return nextPayload.items[0]?.branch ?? "";
      });
    } catch (error) {
      setToast(error instanceof Error ? error.message : "刷新失败");
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshLog = useCallback(async (branch: string) => {
    if (!branch) {
      setLogPayload({ branch: "", path: "", content: "" });
      return;
    }
    setLogPayload(await fetchJson<LogPayload>(`/api/logs?branch=${encodeURIComponent(branch)}`));
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const refreshTimer = window.setInterval(() => {
      void refresh();
    }, 10000);
    const logTimer = window.setInterval(() => {
      if (selected?.branch) void refreshLog(selected.branch);
    }, 1000);
    return () => {
      window.clearInterval(refreshTimer);
      window.clearInterval(logTimer);
    };
  }, [refresh, refreshLog, selected?.branch]);

  useEffect(() => {
    if (!scheduler) return;
    setSchedulerHour(String(scheduler.schedule_hour));
    setSchedulerMinute(String(scheduler.schedule_minute));
  }, [scheduler?.schedule_hour, scheduler?.schedule_minute]);

  useEffect(() => {
    if (!config) return;
    setBranchSummaryFields((config.branch_summary_fields ?? []).join("\n"));
    setPromptFields(config.prompt.fields.join("\n"));
    setPromptContextPaths(config.prompt.context_paths.join("\n"));
    setPromptTemplate(config.prompt.template);
    setMaxConcurrency(String(config.max_concurrency));
  }, [config]);

  useEffect(() => {
    void refreshLog(selected?.branch ?? "");
  }, [refreshLog, selected?.branch]);

  useEffect(() => {
    const element = logPaneRef.current;
    if (!element) return;
    element.scrollTop = element.scrollHeight;
  }, [logPayload.branch, logPayload.content]);

  const postAction = async (path: string, body: Record<string, unknown>, success: string) => {
    setBusyAction(path);
    setToast("");
    try {
      const data = await fetchJson<{ ok?: boolean }>(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      });
      if (data.ok === false) throw new Error("操作失败");
      setToast(success);
      await refresh();
      if (selected?.branch) await refreshLog(selected.branch);
    } catch (error) {
      setToast(error instanceof Error ? error.message : "操作失败");
    } finally {
      setBusyAction("");
    }
  };

  const uploadExcel = async () => {
    if (!excelFile) {
      setToast("请先选择一个 .xlsx 文件");
      return;
    }
    const form = new FormData();
    form.append("file", excelFile);
    setBusyAction("/api/excel/upload");
    setToast("");
    try {
      const apiPort = config?.api_port ?? 8766;
      const uploadUrl = `http://127.0.0.1:${apiPort}/api/excel/upload`;
      const data = await fetchJson<{ ok?: boolean; excel_path: string; file?: ConfigPayload["excel_file"] }>(uploadUrl, { method: "POST", body: form });
      if (data.ok === false) throw new Error("上传失败");
      setToast(`已上传并切换：${excelFile.name}，${formatBytes(data.file?.size)}`);
      setExcelFile(null);
      await refresh();
    } catch (error) {
      setToast(error instanceof Error ? error.message : "上传失败");
    } finally {
      setBusyAction("");
    }
  };

  const selectExcelPath = async () => {
    if (!excelPathInput.trim()) {
      setToast("请输入本机 xlsx 文件路径");
      return;
    }
    await postAction("/api/excel/select-path", { path: excelPathInput.trim() }, "已切换到本机 Excel 路径");
  };

  const runBug = async (bug: BugItem) => {
    setBusyAction(`run-${bug.excel_row}`);
    setToast("");
    try {
      const data = await fetchJson<{ ok?: boolean; branch: string; status: string }>(`/api/bugs/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ excel_row: bug.excel_row })
      });
      if (data.ok === false) throw new Error("执行失败");
      setSelectedBranch(data.branch || bug.branch);
      setToast(`已开始执行：${bug.branch}`);
      await refresh();
      await refreshLog(data.branch || bug.branch);
    } catch (error) {
      setToast(error instanceof Error ? error.message : "执行失败");
    } finally {
      setBusyAction("");
    }
  };

  const deleteBug = async (bug: BugItem) => {
    setBusyAction(`delete-${bug.excel_row}`);
    setToast("");
    try {
      const data = await fetchJson<{ ok?: boolean; branch: string }>(`/api/bugs/delete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ excel_row: bug.excel_row })
      });
      if (data.ok === false) throw new Error("删除失败");
      setToast(`已删除：${bug.branch}`);
      await refresh();
      if (selected?.branch === data.branch) {
        setSelectedBranch("");
        await refreshLog("");
      }
    } catch (error) {
      setToast(error instanceof Error ? error.message : "删除失败");
    } finally {
      setBusyAction("");
    }
  };

  const installSchedule = () => {
    const hour = Number(schedulerHour);
    const minute = Number(schedulerMinute);
    if (!Number.isInteger(hour) || hour < 0 || hour > 23 || !Number.isInteger(minute) || minute < 0 || minute > 59) {
      setToast("任务时间必须是 00:00 到 23:59");
      return;
    }
    void postAction("/api/scheduler/install", { hour, minute }, "定时任务已开启/更新");
  };

  const saveAutomationConfig = () => {
    const concurrency = Number(maxConcurrency);
    if (!Number.isInteger(concurrency) || concurrency < 1 || concurrency > 8) {
      setToast("最高并发数必须在 1-8 之间");
      return;
    }
    void postAction(
      "/api/config/update",
      {
        max_concurrency: concurrency,
        branch_summary_fields: splitLines(branchSummaryFields),
        prompt: {
          fields: splitLines(promptFields),
          template: promptTemplate,
          context_paths: splitLines(promptContextPaths)
        }
      },
      "配置已保存"
    );
  };

  return (
    <main className="consoleShell">
      <aside className="queueRail">
        <div className="brand">
          <div className="brandMark"><Code2 size={20} /></div>
          <div>
            <h1>自动修复控制台</h1>
            <p>{selectedWorkspace?.name ?? "工作区"} · {config?.assignee ?? "对接人"}</p>
          </div>
        </div>

        <div className="metricGrid">
          <Metric value={bugs.length} label="Excel 命中" />
          <Metric value={pendingItems.length} label="待审批" />
          <Metric value={cleanItems.length} label="可清理" />
        </div>

        <button className="railButton" onClick={() => void refresh()} disabled={loading}>
          <RefreshCw size={16} className={loading ? "spin" : ""} />
          刷新
        </button>

        <section className="queueSection">
          <h2>状态说明</h2>
          <div className="statusGuide">
            <div><span className="statusDot running" />正在执行：Codex 还在分析、修改或验证，先不要审批。</div>
            <div><span className="statusDot pending" />已完成待审批：可以查看 diff 和日志，再决定通过或重新修改。</div>
            <div><span className="statusDot clean" />已结束无改动：这次没有生成可提交的前端变更。</div>
          </div>
        </section>

        <section className="queueSection">
          <h2>待审批分支</h2>
          {pendingItems.length === 0 ? <p className="emptyText">暂无待审批改动</p> : null}
          {pendingItems.map(item => (
            <BranchButton key={item.branch} item={item} active={item.branch === selected?.branch} onClick={() => setSelectedBranch(item.branch)} />
          ))}
        </section>

        <section className="queueSection">
          <h2>已无 diff</h2>
          {cleanItems.length === 0 ? <p className="emptyText">暂无残留工作目录</p> : null}
          {cleanItems.map(item => (
            <BranchButton key={item.branch} item={item} active={item.branch === selected?.branch} onClick={() => setSelectedBranch(item.branch)} />
          ))}
        </section>
      </aside>

      <section className="mainStage">
        <header className="commandBar">
          <div>
            <p className="kicker">当前工作区</p>
            <h2>{selectedWorkspace?.name ?? "PC Web"}</h2>
            <p className="path">{config?.target_repo} · {config?.target_app_path}</p>
          </div>
          <div className="commandActions">
            <select
              value={config?.active_workspace ?? ""}
              onChange={event => void postAction("/api/workspace/select", { workspace_id: event.target.value }, "工作区已切换")}
            >
              {(config?.workspaces ?? []).map(workspace => <option key={workspace.id} value={workspace.id}>{workspace.name}</option>)}
            </select>
            <button className="button ghost" onClick={() => void refresh()} disabled={loading}>
              <RefreshCw size={16} className={loading ? "spin" : ""} />
              刷新
            </button>
          </div>
        </header>

        {toast ? <div className="toast">{toast}</div> : null}

        <section className="controlGrid">
          <Panel title="Bug 文档" icon={<Upload size={16} />} aside={compactPath(config?.excel_path)}>
            <div className="documentBody">
              <div>
                <strong>当前读取文件</strong>
                <p>{config?.excel_path ?? "未读取配置"}</p>
                {config?.excel_file?.sha256 ? (
                  <div className="fileMeta">
                    <code>{config.excel_file.original_name}</code>
                    <span>{formatBytes(config.excel_file.size)} · 修改时间 {config.excel_file.mtime}</span>
                    <span>sha256 {config.excel_file.sha256.slice(0, 16)}</span>
                  </div>
                ) : null}
              </div>
              <div className="uploadControl">
                <input
                  id="excelUploadInput"
                  className="fileInput"
                  type="file"
                  accept=".xlsx"
                  onClick={event => { event.currentTarget.value = ""; }}
                  onChange={event => setExcelFile(event.target.files?.[0] ?? null)}
                />
                <label className="filePicker" htmlFor="excelUploadInput"><FileText size={16} />选择 xlsx</label>
                <span className="fileName">{excelFile ? `${excelFile.name} · ${formatBytes(excelFile.size)}` : "未选择文件"}</span>
                <button className="button secondary" disabled={Boolean(busyAction) || !excelFile} onClick={() => void uploadExcel()}>
                  {busyAction === "/api/excel/upload" ? <Loader2 size={16} className="spin" /> : <Upload size={16} />}
                  上传并切换
                </button>
              </div>
              <div className="pathSwitch">
                <input value={excelPathInput} onChange={event => setExcelPathInput(event.target.value)} placeholder="/Users/xiehaojie/Desktop/亦城数智人在线清单.xlsx" />
                <button className="button ghost" disabled={Boolean(busyAction)} onClick={() => void selectExcelPath()}>
                  使用本机路径
                </button>
              </div>
            </div>
          </Panel>

          <Panel title="定时任务" icon={<Timer size={16} />} aside={scheduler?.label}>
            <div className="schedulerBody">
              <div className="schedulerStatus">
                <Badge tone={scheduler?.loaded ? "green" : scheduler?.installed ? "blue" : "gray"}>
                  {scheduler?.loaded ? "已开启" : scheduler?.installed ? "已安装未加载" : "未安装"}
                </Badge>
                <strong>每天 {String(scheduler?.schedule_hour ?? 22).padStart(2, "0")}:{String(scheduler?.schedule_minute ?? 0).padStart(2, "0")} 自动执行</strong>
                <span>{scheduler?.plist_path}</span>
              </div>
              <div className="schedulerActions">
                <label className="timeField"><span>小时</span><input value={schedulerHour} onChange={event => setSchedulerHour(event.target.value)} inputMode="numeric" /></label>
                <label className="timeField"><span>分钟</span><input value={schedulerMinute} onChange={event => setSchedulerMinute(event.target.value)} inputMode="numeric" /></label>
                <button className="button ghost" disabled={Boolean(busyAction)} onClick={installSchedule}><Save size={16} />保存并开启</button>
                <button className="button ghost" disabled={Boolean(busyAction) || !scheduler?.installed} onClick={() => void postAction("/api/scheduler/uninstall", {}, "定时任务已取消")}><Power size={16} />取消定时</button>
                <button className="button secondary" disabled={Boolean(busyAction)} onClick={() => void postAction("/api/run-once", {}, "已开始手动执行，日志写入 logs/manual-run-*.log")}>
                  {busyAction === "/api/run-once" ? <Loader2 size={16} className="spin" /> : <PlayCircle size={16} />}
                  立即执行一次
                </button>
              </div>
            </div>
          </Panel>
        </section>

        <Panel title="Excel 筛选结果" icon={<Database size={16} />} aside={`${bugs.length} 条待处理`}>
          <BugTable bugs={bugs} busyAction={busyAction} onRun={runBug} onDelete={deleteBug} />
        </Panel>

        <section className="reviewGrid">
          <div className="reviewMain">
            {selected ? (
              <>
                <Panel title="审批操作" icon={<CheckCircle2 size={16} />} aside={selected.branch}>
                  <div className="approvalBar">
                    <button className="button primary" disabled={actionDisabled || selected.active || !selected.pending} onClick={() => void postAction("/api/approve", { branch: selected.branch }, "已提交并移除 worktree")}>
                      {busyAction === "/api/approve" ? <Loader2 size={16} className="spin" /> : <CheckCircle2 size={16} />}
                      通过并提交到 fix 分支
                    </button>
                    <button className="button danger" disabled={actionDisabled || selected.active} onClick={() => void postAction("/api/reject", { branch: selected.branch }, "已拒绝并删除分支")}><Trash2 size={16} />拒绝删除</button>
                    <button className="button ghost" disabled={actionDisabled || selected.active || selected.pending} onClick={() => void postAction("/api/cleanup", { branch: selected.branch }, "已清理工作目录")}><XCircle size={16} />清理残留</button>
                  </div>
                  <TaskState item={selected} />
                  <div className="fileList">
                    {selected.changed_files.length > 0 ? selected.changed_files.map(file => <code key={file}>{file}</code>) : <span>没有待处理改动</span>}
                  </div>
                </Panel>

                <Panel title="重新修改" icon={<RotateCcw size={16} />}>
                  <div className="formGrid">
                    <label><span><MessageSquareText size={14} />补充文字</span><textarea value={note} onChange={event => setNote(event.target.value)} placeholder="补充验收标准、异常表现或期望交互" /></label>
                    <label><span><FileText size={14} />补充文件路径</span><textarea value={filePaths} onChange={event => setFilePaths(event.target.value)} placeholder="/Users/xiehaojie/Desktop/补充说明.md" /></label>
                    <label><span><ImagePlus size={14} />补充图片路径</span><textarea value={imagePaths} onChange={event => setImagePaths(event.target.value)} placeholder="/Users/xiehaojie/Desktop/screenshot.png" /></label>
                  </div>
                  <button className="button secondary" disabled={actionDisabled || selected.active} onClick={() => void postAction("/api/rework", { branch: selected.branch, note, file_paths: splitLines(filePaths), image_paths: splitLines(imagePaths) }, "已提交给 Codex 重新修改，请稍后刷新")}>
                    {busyAction === "/api/rework" ? <Loader2 size={16} className="spin" /> : <RotateCcw size={16} />}
                    让 Codex 重新修改
                  </button>
                </Panel>

                <Panel title="代码比对" icon={<GitBranch size={16} />}>
                  <DiffView diff={selected.diff} />
                </Panel>
              </>
            ) : (
              <div className="blankState">
                <Clock3 size={32} />
                <h2>没有待处理的修复</h2>
                <p>晚上自动化跑完后，这里会出现每条 bug 的独立分支和 diff。</p>
              </div>
            )}
          </div>

          <aside className="inspector">
            <Panel title="Codex 日志" icon={<TerminalSquare size={16} />} aside={compactPath(logPayload.path)}>
              <pre ref={logPaneRef} className="logPane">{logPayload.content || "当前分支暂无 Codex 执行日志。"}</pre>
            </Panel>

            <Panel title="自动化配置" icon={<Settings2 size={16} />}>
              <div className="configStack">
                <label><span>最高并发数</span><input value={maxConcurrency} onChange={event => setMaxConcurrency(event.target.value)} inputMode="numeric" /></label>
                <label><span>分支摘要字段</span><textarea value={branchSummaryFields} onChange={event => setBranchSummaryFields(event.target.value)} placeholder="问题描述\n备注" /></label>
                <label><span>提示词字段</span><textarea value={promptFields} onChange={event => setPromptFields(event.target.value)} /></label>
                <label><span>工程上下文路径</span><textarea value={promptContextPaths} onChange={event => setPromptContextPaths(event.target.value)} placeholder="apps/pc-web/src/app" /></label>
                <label><span>初始化提示词</span><textarea value={promptTemplate} onChange={event => setPromptTemplate(event.target.value)} /></label>
                <button className="button secondary" onClick={saveAutomationConfig} disabled={Boolean(busyAction)}><Save size={16} />保存配置</button>
              </div>
            </Panel>

            <Panel title="筛选规则" icon={<Database size={16} />}>
              <div className="ruleList">
                {(config?.filters ?? []).map(rule => (
                  <div className="ruleItem" key={`${rule.field}-${rule.op}`}>
                    <strong>{rule.field}</strong>
                    <span>{rule.op}</span>
                    <code>{(rule.values?.length ? rule.values : [rule.value]).filter(Boolean).join(", ") || "空"}</code>
                  </div>
                ))}
              </div>
            </Panel>
          </aside>
        </section>
      </section>
    </main>
  );
}

async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { cache: "no-store", ...init });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.ok === false) {
    throw new Error(data.error || `请求失败: ${response.status}`);
  }
  return data as T;
}

function Metric({ value, label }: { value: number; label: string }) {
  return <div className="metric"><strong>{value}</strong><span>{label}</span></div>;
}

function Panel({ title, icon, aside, children }: { title: string; icon: ReactNode; aside?: string; children: ReactNode }) {
  return (
    <section className="panel">
      <div className="panelTitle">
        <div>{icon}<h3>{title}</h3></div>
        {aside ? <span>{aside}</span> : null}
      </div>
      {children}
    </section>
  );
}

function BranchButton({ item, active, onClick }: { item: FixItem; active: boolean; onClick: () => void }) {
  return (
    <button className={`branchButton ${active ? "active" : ""}`} onClick={onClick}>
      <span className={`statusDot ${item.active ? "running" : item.pending ? "pending" : "clean"}`} />
      <div className="branchCopy">
        <strong>{item.branch.replace("fix/", "")}</strong>
        <small>{taskHeadline(item)}</small>
      </div>
      <span className="branchMeta">{item.active ? phaseLabel(item.task_phase) : `${item.changed_files.length} 个改动文件`}</span>
    </button>
  );
}

function TaskState({ item }: { item: FixItem }) {
  return (
    <div className={`taskState ${item.active ? "active" : ""}`}>
      <span className={`statusDot ${taskTone(item)}`} />
      <div className="taskStateCopy">
        <strong>{taskHeadline(item)}</strong>
        <span>{taskSubtext(item)}</span>
      </div>
      {item.task_updated_at ? <code>{item.task_updated_at}</code> : null}
    </div>
  );
}

function Badge({ children, tone = "green" }: { children: string; tone?: "green" | "blue" | "gray" }) {
  return <span className={`badge ${tone}`}>{children || "未填"}</span>;
}

function BugTable({
  bugs,
  busyAction,
  onRun,
  onDelete
}: {
  bugs: BugItem[];
  busyAction: string;
  onRun: (bug: BugItem) => void | Promise<void>;
  onDelete: (bug: BugItem) => void | Promise<void>;
}) {
  if (bugs.length === 0) return <div className="noDiff">当前 Excel 没有命中筛选规则的 bug。</div>;
  return (
    <div className="excelTableWrap">
      <table className="excelTable">
        <thead>
          <tr>
            <th>序号</th>
            <th>行</th>
            <th>截图</th>
            <th>来源</th>
            <th>分类</th>
            <th>状态</th>
            <th>问题描述</th>
            <th>备注</th>
            <th>管理</th>
          </tr>
        </thead>
        <tbody>
          {bugs.map(bug => (
            <tr key={`${bug.issue_id}-${bug.excel_row}`}>
              <td><strong>{bug.issue_id}</strong></td>
              <td>{bug.excel_row}</td>
              <td><ScreenshotCell bug={bug} /></td>
              <td>{bug.source_system}</td>
              <td><div className="categoryCell"><span>{bug.primary_category || "未填"}</span><small>{bug.secondary_category || "未填"}</small></div></td>
              <td><div className="statusStack"><Badge>{bug.requester_status}</Badge><Badge tone={bug.assignee_status ? "blue" : "gray"}>{bug.assignee_status || "未填"}</Badge></div></td>
              <td><div className="descriptionCell"><span>{bug.description || "未填写问题描述"}</span><small>{bug.branch}</small></div></td>
              <td><div className="remarkCell"><span>{bug.remark || "无"}</span>{bug.remark2 ? <small>{bug.remark2}</small> : null}</div></td>
              <td>
                <div className="rowActions">
                  <button className="iconTextButton primaryLite" disabled={bug.active || Boolean(busyAction)} onClick={() => void onRun(bug)}>
                    {busyAction === `run-${bug.excel_row}` ? <Loader2 size={14} className="spin" /> : <PlayCircle size={14} />}
                    执行
                  </button>
                  <button className="iconTextButton dangerLite" disabled={bug.active || Boolean(busyAction)} onClick={() => void onDelete(bug)}>
                    {busyAction === `delete-${bug.excel_row}` ? <Loader2 size={14} className="spin" /> : <Trash2 size={14} />}
                    删除
                  </button>
                  <small>{taskHeadline(bug)}{bug.task_detail ? ` · ${bug.task_detail}` : ""}</small>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ScreenshotCell({ bug }: { bug: BugItem }) {
  if (!bug.images?.length) return <span className="mutedText">无</span>;
  return (
    <div className="screenshotCell">
      {bug.images.map(image => (
        <a key={image.path} href={image.url} target="_blank" rel="noreferrer" title={image.name}>
          <img src={image.url} alt={`Bug ${bug.issue_id} 截图 ${image.name}`} />
        </a>
      ))}
    </div>
  );
}

function DiffView({ diff }: { diff: string }) {
  if (!diff.trim()) return <div className="noDiff">没有当前工作区 diff。</div>;
  return (
    <div className="diff">
      {diff.split("\n").map((line, index) => {
        const kind = line.startsWith("+") && !line.startsWith("+++")
          ? "add"
          : line.startsWith("-") && !line.startsWith("---")
            ? "del"
            : line.startsWith("@@")
              ? "hunk"
              : line.startsWith("diff --git")
                ? "file"
                : "";
        return <pre key={`${index}-${line}`} className={kind}>{line || " "}</pre>;
      })}
    </div>
  );
}

function compactPath(value?: string) {
  if (!value) return "";
  if (value.length <= 64) return value;
  return `...${value.slice(-61)}`;
}

function formatBytes(value?: number) {
  if (!value) return "0 B";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function taskHeadline(item: TaskLike) {
  if (item.active) return "Codex 正在执行";
  if (item.task_status === "pending-approval") return "Codex 已完成，等待你审批";
  if (item.task_status === "failed") return "执行失败，需要重新触发";
  if (item.task_status === "no-change") return "Codex 已结束，没有产出前端改动";
  if (item.task_status === "skipped") return "任务已跳过";
  if (item.pending) return "等待你审批";
  return "当前空闲";
}

function taskSubtext(item: TaskLike) {
  if (item.active) {
    return `${phaseLabel(item.task_phase)}${item.task_detail ? ` · ${item.task_detail}` : ""}`;
  }
  if (item.task_status === "pending-approval") return item.task_detail || "可以先看代码比对，再决定是否通过或重新修改。";
  if (item.task_status === "failed") return item.task_detail || "请打开 Codex 日志，查看失败原因。";
  if (item.task_status === "no-change") return item.task_detail || "Codex 跑完了，但没有生成可提交的前端改动。";
  if (item.task_status === "skipped") return item.task_detail || "这个任务被系统跳过了。";
  return item.pending ? "还在待审批队列里。" : "当前没有需要处理的任务。";
}

function taskTone(item: TaskLike) {
  if (item.active) return "running";
  if (item.task_status === "failed") return "failed";
  if (item.task_status === "pending-approval") return "pending";
  return "clean";
}

function phaseLabel(phase: string) {
  if (phase === "prepare") return "正在准备 worktree";
  if (phase === "codex") return "Codex 正在分析并修改";
  if (phase === "verify") return "正在执行校验命令";
  if (phase === "done") return "已结束";
  if (phase === "queued") return "正在排队";
  if (phase === "failed") return "执行失败";
  if (phase === "reworking") return "正在根据补充信息重新修改";
  return "处理中";
}
