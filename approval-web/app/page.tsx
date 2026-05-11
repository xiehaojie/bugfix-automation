"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
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
  RefreshCw,
  RotateCcw,
  Timer,
  Trash2,
  XCircle
} from "lucide-react";

type FixItem = {
  branch: string;
  path: string;
  changed_files: string[];
  pending: boolean;
  status: string;
  diff: string;
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
  priority: string;
  primary_category: string;
  secondary_category: string;
  requester: string;
  request_date: string;
  requester_status: string;
  assignee: string;
  assignee_status: string;
  resolved_date: string;
  description: string;
  remark: string;
  remark2: string;
  images: Array<{ path: string; name: string; url: string }>;
};

type BugsPayload = {
  bugs: BugItem[];
};

type ConfigPayload = {
  target_repo: string;
  target_app_path: string;
  excel_path: string;
  assignee: string;
  web_port: number;
  api_port: number;
};

type SchedulerPayload = {
  label: string;
  plist_path: string;
  installed: boolean;
  loaded: boolean;
  detail: string;
  schedule_hour: number;
  schedule_minute: number;
  stdout_log: string;
  stderr_log: string;
};

const splitLines = (value: string) =>
  value
    .split("\n")
    .map(line => line.trim())
    .filter(Boolean);

export default function ApprovalPage() {
  const [payload, setPayload] = useState<DashboardPayload>({ pending_count: 0, items: [] });
  const [bugsPayload, setBugsPayload] = useState<BugsPayload>({ bugs: [] });
  const [scheduler, setScheduler] = useState<SchedulerPayload | null>(null);
  const [config, setConfig] = useState<ConfigPayload | null>(null);
  const [selectedBranch, setSelectedBranch] = useState("");
  const [loading, setLoading] = useState(true);
  const [busyAction, setBusyAction] = useState("");
  const [toast, setToast] = useState("");
  const [note, setNote] = useState("");
  const [filePaths, setFilePaths] = useState("");
  const [imagePaths, setImagePaths] = useState("");

  const selected = useMemo(
    () => payload.items.find(item => item.branch === selectedBranch) ?? payload.items[0],
    [payload.items, selectedBranch]
  );

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [itemsRes, bugsRes, configRes, schedulerRes] = await Promise.all([
        fetch("/api/items"),
        fetch("/api/bugs"),
        fetch("/api/config"),
        fetch("/api/scheduler")
      ]);
      const nextPayload = (await itemsRes.json()) as DashboardPayload;
      const nextBugsPayload = (await bugsRes.json()) as BugsPayload;
      const nextConfig = (await configRes.json()) as ConfigPayload;
      const nextScheduler = (await schedulerRes.json()) as SchedulerPayload;
      setPayload(nextPayload);
      setBugsPayload(nextBugsPayload);
      setConfig(nextConfig);
      setScheduler(nextScheduler);
      setSelectedBranch(current => {
        if (current && nextPayload.items.some(item => item.branch === current)) return current;
        return nextPayload.items[0]?.branch ?? "";
      });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      void refresh();
    }, 30000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const postAction = async (path: string, body: Record<string, unknown>, success: string) => {
    setBusyAction(path);
    setToast("");
    try {
      const res = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      });
      const data = await res.json();
      if (!res.ok || data.ok === false) throw new Error(data.error || "操作失败");
      setToast(success);
      await refresh();
    } catch (error) {
      setToast(error instanceof Error ? error.message : "操作失败");
    } finally {
      setBusyAction("");
    }
  };

  const pendingItems = payload.items.filter(item => item.pending);
  const cleanItems = payload.items.filter(item => !item.pending);
  const bugRows = bugsPayload.bugs ?? [];
  const actionDisabled = Boolean(busyAction) || !selected;

  return (
    <main className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brandMark"><Code2 size={20} /></div>
          <div>
            <h1>Bug 修复审批台</h1>
            <p>{config?.assignee ?? "谢浩杰"} · pc-web</p>
          </div>
        </div>

        <div className="metricGrid">
          <div className="metric">
            <span>{payload.pending_count}</span>
            <p>待处理</p>
          </div>
          <div className="metric">
            <span>{cleanItems.length}</span>
            <p>可清理</p>
          </div>
          <div className="metric metricWide">
            <span>{bugRows.length}</span>
            <p>Excel 命中</p>
          </div>
        </div>

        <button className="toolButton" onClick={() => void refresh()} disabled={loading}>
          <RefreshCw size={16} className={loading ? "spin" : ""} />
          刷新状态
        </button>

        <section className="branchGroup">
          <h2>待审批</h2>
          {pendingItems.length === 0 ? <p className="emptyText">暂无待审批改动</p> : null}
          {pendingItems.map(item => (
            <BranchButton key={item.branch} item={item} active={item.branch === selected?.branch} onClick={() => setSelectedBranch(item.branch)} />
          ))}
        </section>

        <section className="branchGroup">
          <h2>已无 diff</h2>
          {cleanItems.length === 0 ? <p className="emptyText">暂无残留工作目录</p> : null}
          {cleanItems.map(item => (
            <BranchButton key={item.branch} item={item} active={item.branch === selected?.branch} onClick={() => setSelectedBranch(item.branch)} />
          ))}
        </section>
      </aside>

      <section className="content">
        <header className="topbar">
          <div>
            <p className="eyebrow">本地工作区</p>
            <h2>{selected?.branch ?? "暂无修复分支"}</h2>
            <p className="path">{selected?.path ?? config?.target_repo}</p>
          </div>
          <div className="topActions">
            <button
              className="button primary"
              disabled={actionDisabled || !selected?.pending}
              onClick={() => selected && void postAction("/api/approve", { branch: selected.branch }, "已提交并移除 worktree")}
            >
              {busyAction === "/api/approve" ? <Loader2 size={16} className="spin" /> : <CheckCircle2 size={16} />}
              通过并提交
            </button>
            <button
              className="button danger"
              disabled={actionDisabled || !selected}
              onClick={() => selected && void postAction("/api/reject", { branch: selected.branch }, "已拒绝并删除分支")}
            >
              <Trash2 size={16} />
              拒绝删除
            </button>
            <button
              className="button ghost"
              disabled={actionDisabled || !selected || selected.pending}
              onClick={() => selected && void postAction("/api/cleanup", { branch: selected.branch }, "已清理工作目录")}
            >
              <XCircle size={16} />
              清理残留
            </button>
          </div>
        </header>

        {toast ? <div className="toast">{toast}</div> : null}

        <section className="panel schedulerPanel">
          <div className="panelTitle spread">
            <div>
              <Timer size={16} />
              <h3>定时任务</h3>
            </div>
            <span>{scheduler?.label}</span>
          </div>
          <div className="schedulerBody">
            <div className="schedulerStatus">
              <Badge tone={scheduler?.loaded ? "green" : scheduler?.installed ? "blue" : "gray"}>
                {scheduler?.loaded ? "已开启" : scheduler?.installed ? "已安装未加载" : "未安装"}
              </Badge>
              <strong>
                每天 {String(scheduler?.schedule_hour ?? 22).padStart(2, "0")}:
                {String(scheduler?.schedule_minute ?? 0).padStart(2, "0")} 自动执行
              </strong>
              <span>{scheduler?.plist_path}</span>
            </div>
            <div className="schedulerActions">
              <button
                className="button ghost"
                disabled={Boolean(busyAction)}
                onClick={() => void postAction("/api/scheduler/install", {}, "定时任务已安装/重新加载")}
              >
                <Timer size={16} />
                开启定时
              </button>
              <button
                className="button secondary"
                disabled={Boolean(busyAction)}
                onClick={() => void postAction("/api/run-once", {}, "已开始手动执行，日志写入 logs/manual-run-*.log")}
              >
                {busyAction === "/api/run-once" ? <Loader2 size={16} className="spin" /> : <PlayCircle size={16} />}
                立即执行一次
              </button>
            </div>
          </div>
        </section>

        <section className="panel excelPanel">
          <div className="panelTitle spread">
            <div>
              <Database size={16} />
              <h3>Excel 筛选结果</h3>
            </div>
            <span>{config?.excel_path}</span>
          </div>
          <div className="excelTableWrap">
            {bugRows.length > 0 ? (
              <table className="excelTable">
                <thead>
                  <tr>
                    <th>序号</th>
                    <th>Excel 行</th>
                    <th>截图</th>
                    <th>来源</th>
                    <th>分类</th>
                    <th>提出人状态</th>
                    <th>对接人状态</th>
                    <th>问题描述</th>
                    <th>备注</th>
                  </tr>
                </thead>
                <tbody>
                  {bugRows.map(bug => (
                    <tr key={`${bug.issue_id}-${bug.excel_row}`}>
                      <td><strong>{bug.issue_id}</strong></td>
                      <td>{bug.excel_row}</td>
                      <td>
                        <div className="screenshotCell">
                          {(bug.images ?? []).length > 0 ? bug.images.map(image => (
                            <a key={image.path} href={image.url} target="_blank" rel="noreferrer" title={image.name}>
                              <img src={image.url} alt={`Bug ${bug.issue_id} 截图 ${image.name}`} />
                            </a>
                          )) : <span>无</span>}
                        </div>
                      </td>
                      <td>{bug.source_system}</td>
                      <td>
                        <div className="categoryCell">
                          <span>{bug.primary_category || "未填"}</span>
                          <small>{bug.secondary_category || "未填"}</small>
                        </div>
                      </td>
                      <td><Badge>{bug.requester_status}</Badge></td>
                      <td><Badge tone={bug.assignee_status ? "blue" : "gray"}>{bug.assignee_status || "未填"}</Badge></td>
                      <td>
                        <div className="descriptionCell">
                          <span>{bug.description || "未填写问题描述"}</span>
                          <small>{bug.branch}</small>
                        </div>
                      </td>
                      <td>
                        <div className="remarkCell">
                          <span>{bug.remark || "无"}</span>
                          {bug.remark2 ? <small>{bug.remark2}</small> : null}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="noDiff">当前 Excel 没有命中筛选规则的 bug。</div>
            )}
          </div>
        </section>

        {selected ? (
          <div className="workspace">
            <section className="panel">
              <div className="panelTitle">
                <FileText size={16} />
                <h3>改动文件</h3>
              </div>
              <div className="fileList">
                {selected.changed_files.length > 0 ? selected.changed_files.map(file => <code key={file}>{file}</code>) : <span>没有 pc-web 待处理改动</span>}
              </div>
            </section>

            <section className="panel rework">
              <div className="panelTitle">
                <RotateCcw size={16} />
                <h3>重新修改</h3>
              </div>
              <div className="formGrid">
                <label>
                  <span><MessageSquareText size={14} /> 补充文字</span>
                  <textarea value={note} onChange={event => setNote(event.target.value)} placeholder="例如：空状态不要上传图标，上传中需要禁用重复点击..." />
                </label>
                <label>
                  <span><FileText size={14} /> 补充文件路径</span>
                  <textarea value={filePaths} onChange={event => setFilePaths(event.target.value)} placeholder="/Users/xiehaojie/Desktop/补充说明.md" />
                </label>
                <label>
                  <span><ImagePlus size={14} /> 补充图片路径</span>
                  <textarea value={imagePaths} onChange={event => setImagePaths(event.target.value)} placeholder="/Users/xiehaojie/Desktop/screenshot.png" />
                </label>
              </div>
              <button
                className="button secondary"
                disabled={actionDisabled}
                onClick={() =>
                  selected &&
                  void postAction(
                    "/api/rework",
                    { branch: selected.branch, note, file_paths: splitLines(filePaths), image_paths: splitLines(imagePaths) },
                    "已提交给 Codex 重新修改，请刷新查看 diff"
                  )
                }
              >
                {busyAction === "/api/rework" ? <Loader2 size={16} className="spin" /> : <RotateCcw size={16} />}
                让 Codex 重新修改
              </button>
            </section>

            <section className="panel diffPanel">
              <div className="panelTitle">
                <GitBranch size={16} />
                <h3>代码比对</h3>
              </div>
              <DiffView diff={selected.diff} />
            </section>
          </div>
        ) : (
          <div className="blankState">
            <Clock3 size={32} />
            <h2>没有待处理的修复</h2>
            <p>晚上自动化跑完后，这里会出现每条 bug 的独立分支和 diff。</p>
          </div>
        )}
      </section>
    </main>
  );
}

function BranchButton({ item, active, onClick }: { item: FixItem; active: boolean; onClick: () => void }) {
  return (
    <button className={`branchButton ${active ? "active" : ""}`} onClick={onClick}>
      <span className={`statusDot ${item.pending ? "pending" : "clean"}`} />
      <span>{item.branch.replace("fix/", "")}</span>
      <small>{item.changed_files.length} 个文件</small>
    </button>
  );
}

function Badge({ children, tone = "green" }: { children: string; tone?: "green" | "blue" | "gray" }) {
  return <span className={`badge ${tone}`}>{children || "未填"}</span>;
}

function DiffView({ diff }: { diff: string }) {
  if (!diff.trim()) return <div className="noDiff">没有 pc-web diff。</div>;
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
        return (
          <pre key={`${index}-${line}`} className={kind}>
            {line || " "}
          </pre>
        );
      })}
    </div>
  );
}
