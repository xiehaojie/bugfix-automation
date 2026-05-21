"use client";

import { useCallback, useEffect, useState } from "react";
import { BadgeCheck, GitMerge, Loader2, Play, Trash2, XCircle } from "lucide-react";
import {
  createIntegrationRun,
  fetchIntegrationDiff,
  fetchIntegrationRuns,
  startIntegrationRun,
  confirmIntegrationRun,
  cleanupIntegrationRun,
  abortIntegrationRun,
} from "../api";
import type { IntegrationRun } from "../types";
import { DiffView } from "../../approval/components/DiffView";

const STATUS_LABELS: Record<string, { text: string; tone: string }> = {
  draft: { text: "草稿", tone: "gray" },
  running: { text: "集成中", tone: "blue" },
  blocked: { text: "冲突阻塞", tone: "red" },
  "verify-failed": { text: "验证失败", tone: "orange" },
  "pending-user-approval": { text: "等待确认", tone: "yellow" },
  committed: { text: "已提交", tone: "green" },
  cleaned: { text: "已清理", tone: "green" },
  aborted: { text: "已中止", tone: "gray" },
};

const ITEM_STATUS_LABELS: Record<string, { text: string; cls: string }> = {
  pending: { text: "待应用", cls: "gray" },
  applying: { text: "应用中", cls: "blue" },
  applied: { text: "已应用", cls: "green" },
  conflict: { text: "冲突", cls: "red" },
};

interface Props {
  /** Branches available for integration (from doneItems in approval page) */
  doneBranches: string[];
  workspaceId: string;
  targetBranch: string;
}

export function IntegrationPanel({ doneBranches, workspaceId, targetBranch }: Props) {
  const [runs, setRuns] = useState<IntegrationRun[]>([]);
  const [activeRun, setActiveRun] = useState<IntegrationRun | null>(null);
  const [diff, setDiff] = useState("");
  const [busy, setBusy] = useState("");
  const [toast, setToast] = useState("");
  const [loading, setLoading] = useState(true);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(""), 3000);
  };

  const loadRuns = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchIntegrationRuns();
      setRuns(data);
      // Auto-select the latest non-terminal run (or most recent)
      const active = data.find(r => !["committed", "cleaned", "aborted"].includes(r.status));
      if (active) {
        setActiveRun(active);
        const d = await fetchIntegrationDiff(active.run_id);
        setDiff(d);
      } else if (data.length > 0) {
        setActiveRun(data[0]);
        const d = await fetchIntegrationDiff(data[0].run_id);
        setDiff(d);
      }
    } catch (err) {
      showToast(`加载失败: ${err}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void loadRuns(); }, [loadRuns]);

  const handleCreate = async () => {
    if (doneBranches.length === 0) return;
    setBusy("create");
    try {
      const run = await createIntegrationRun(workspaceId, targetBranch, doneBranches);
      showToast(`集成单已创建，包含 ${doneBranches.length} 个分支`);
      setActiveRun(run);
      await loadRuns();
    } catch (err) {
      showToast(`创建失败: ${err}`);
    } finally {
      setBusy("");
    }
  };

  const handleStart = async () => {
    if (!activeRun) return;
    setBusy("start");
    try {
      const run = await startIntegrationRun(activeRun.run_id);
      setActiveRun(run);
      const d = await fetchIntegrationDiff(activeRun.run_id);
      setDiff(d);
      showToast(`集成完成: ${run.status}`);
      await loadRuns();
    } catch (err) {
      showToast(`失败: ${err}`);
    } finally {
      setBusy("");
    }
  };

  const handleConfirm = async () => {
    if (!activeRun) return;
    setBusy("confirm");
    try {
      const run = await confirmIntegrationRun(activeRun.run_id);
      setActiveRun(run);
      showToast(`已确认提交: ${run.final_commit?.slice(0, 7)}`);
      await loadRuns();
    } catch (err) {
      showToast(`确认失败: ${err}`);
    } finally {
      setBusy("");
    }
  };

  const handleCleanup = async () => {
    if (!activeRun) return;
    setBusy("cleanup");
    try {
      const run = await cleanupIntegrationRun(activeRun.run_id);
      setActiveRun(run);
      showToast(`已清理 ${run.cleaned_branches?.length ?? 0} 个来源分支`);
      await loadRuns();
    } catch (err) {
      showToast(`清理失败: ${err}`);
    } finally {
      setBusy("");
    }
  };

  const handleAbort = async () => {
    if (!activeRun) return;
    setBusy("abort");
    try {
      const run = await abortIntegrationRun(activeRun.run_id);
      setActiveRun(run);
      showToast("已中止");
      await loadRuns();
    } catch (err) {
      showToast(`中止失败: ${err}`);
    } finally {
      setBusy("");
    }
  };

  const selectRun = async (run: IntegrationRun) => {
    setActiveRun(run);
    try {
      const d = await fetchIntegrationDiff(run.run_id);
      setDiff(d);
    } catch { setDiff(""); }
  };

  if (loading) {
    return (
      <div className="intPanelEmpty">
        <Loader2 size={20} className="spin" />
        <span>加载中...</span>
      </div>
    );
  }

  // No active integration run - show create prompt
  if (!activeRun) {
    return (
      <div className="intPanelEmpty">
        <GitMerge size={24} />
        <p>当前没有集成单</p>
        <button className="button primary" disabled={doneBranches.length === 0 || !!busy} onClick={() => void handleCreate()}>
          {busy === "create" ? <Loader2 size={16} className="spin" /> : <GitMerge size={16} />}
          一键集成 {doneBranches.length} 个分支 → {targetBranch}
        </button>
        {doneBranches.length === 0 && <span className="intPanelHint">暂无已完成的分支可集成</span>}
      </div>
    );
  }

  const statusInfo = STATUS_LABELS[activeRun.status] ?? { text: activeRun.status, tone: "gray" };
  const canStart = ["draft", "blocked", "verify-failed"].includes(activeRun.status);
  const canConfirm = ["pending-user-approval", "verify-failed"].includes(activeRun.status);
  const canCleanup = activeRun.status === "committed";
  const canAbort = !["committed", "cleaned", "aborted"].includes(activeRun.status);

  return (
    <div className="intPanel">
      {toast && <div className="toast">{toast}</div>}

      {/* Run switcher if multiple runs */}
      {runs.length > 1 && (
        <div className="intPanelRunSwitcher">
          {runs.map(r => (
            <button
              key={r.run_id}
              className={`intPanelRunChip ${r.run_id === activeRun.run_id ? "active" : ""}`}
              onClick={() => void selectRun(r)}
            >
              <span className={`intStatusDot ${(STATUS_LABELS[r.status] ?? { tone: "gray" }).tone}`} />
              {r.run_id.slice(0, 16)}
            </button>
          ))}
        </div>
      )}

      {/* Header */}
      <div className="intPanelHeader">
        <div className="intPanelHeaderLeft">
          <span className={`intStatusBadge large ${statusInfo.tone}`}>{statusInfo.text}</span>
          <code className="intPanelId">{activeRun.run_id}</code>
        </div>
        <div className="intPanelActions">
          {canStart && (
            <button className="button primary" disabled={!!busy} onClick={() => void handleStart()}>
              {busy === "start" ? <Loader2 size={16} className="spin" /> : <Play size={16} />}
              开始集成
            </button>
          )}
          {canConfirm && (
            <button className="button primary" disabled={!!busy} onClick={() => void handleConfirm()}>
              {busy === "confirm" ? <Loader2 size={16} className="spin" /> : <BadgeCheck size={16} />}
              确认提交
            </button>
          )}
          {canCleanup && (
            <button className="button secondary" disabled={!!busy} onClick={() => void handleCleanup()}>
              {busy === "cleanup" ? <Loader2 size={16} className="spin" /> : <Trash2 size={16} />}
              清理来源分支
            </button>
          )}
          {canAbort && (
            <button className="button danger" disabled={!!busy} onClick={() => void handleAbort()}>
              {busy === "abort" ? <Loader2 size={16} className="spin" /> : <XCircle size={16} />}
              中止
            </button>
          )}
          {/* Allow creating new even when viewing an old one */}
          {["committed", "cleaned", "aborted"].includes(activeRun.status) && doneBranches.length > 0 && (
            <button className="button secondary" disabled={!!busy} onClick={() => void handleCreate()}>
              {busy === "create" ? <Loader2 size={16} className="spin" /> : <GitMerge size={16} />}
              新建集成单
            </button>
          )}
        </div>
      </div>

      {/* Info */}
      <div className="intDetailInfo">
        <div className="intInfoRow">
          <span className="intInfoLabel">目标分支</span>
          <code>{activeRun.target_branch}</code>
        </div>
        <div className="intInfoRow">
          <span className="intInfoLabel">集成分支</span>
          <code>{activeRun.integration_branch}</code>
        </div>
        {activeRun.final_commit && (
          <div className="intInfoRow">
            <span className="intInfoLabel">提交</span>
            <code>{activeRun.final_commit.slice(0, 12)}</code>
          </div>
        )}
        <div className="intInfoRow">
          <span className="intInfoLabel">创建时间</span>
          <span>{activeRun.created_at}</span>
        </div>
      </div>

      {/* Items */}
      <div className="intItemsSection">
        <h4>来源分支 ({activeRun.items.length})</h4>
        <table className="intItemsTable">
          <thead>
            <tr><th>分支</th><th>方式</th><th>状态</th><th>错误</th></tr>
          </thead>
          <tbody>
            {activeRun.items.map(item => {
              const info = ITEM_STATUS_LABELS[item.status] ?? { text: item.status, cls: "gray" };
              return (
                <tr key={item.branch}>
                  <td><code className="intBranchCode">{item.branch}</code></td>
                  <td>{item.apply_method || "—"}</td>
                  <td><span className={`intItemBadge ${info.cls}`}>{info.text}</span></td>
                  <td className="intErrorCell">{item.error || "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* AI */}
      {activeRun.ai_review.summary && (
        <div className="intAiSection">
          <h4>AI 复核</h4>
          <p>{activeRun.ai_review.summary}</p>
        </div>
      )}

      {/* Diff */}
      {diff && (
        <div className="intDiffSection">
          <h4>累计 Diff</h4>
          <DiffView diff={diff} />
        </div>
      )}
    </div>
  );
}
