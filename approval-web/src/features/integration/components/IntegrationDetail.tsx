"use client";

import { BadgeCheck, Ban, Loader2, Play, Trash2, XCircle } from "lucide-react";
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

interface DetailProps {
  run: IntegrationRun;
  diff: string;
  busy: string;
  onStart: () => void;
  onConfirm: () => void;
  onCleanup: () => void;
  onAbort: () => void;
  onDelete: () => void;
}

export function IntegrationDetail({ run, diff, busy, onStart, onConfirm, onCleanup, onAbort, onDelete }: DetailProps) {
  const statusInfo = STATUS_LABELS[run.status] ?? { text: run.status, tone: "gray" };
  const canStart = ["draft", "blocked", "verify-failed"].includes(run.status);
  const canConfirm = ["pending-user-approval", "verify-failed"].includes(run.status);
  const canCleanup = run.status === "committed";
  const canAbort = !["committed", "cleaned", "aborted"].includes(run.status);
  const canDelete = run.status !== "running";

  return (
    <div className="intDetail">
      {/* Header */}
      <div className="intDetailHeader">
        <div className="intDetailMeta">
          <span className={`intStatusBadge large ${statusInfo.tone}`}>{statusInfo.text}</span>
          <span className="intDetailId">{run.run_id}</span>
        </div>
        <div className="intDetailActions">
          {canStart && (
            <button className="button primary" disabled={!!busy} onClick={onStart}>
              {busy === "start" ? <Loader2 size={16} className="spin" /> : <Play size={16} />}
              开始集成
            </button>
          )}
          {canConfirm && (
            <button className="button primary" disabled={!!busy} onClick={onConfirm}>
              {busy === "confirm" ? <Loader2 size={16} className="spin" /> : <BadgeCheck size={16} />}
              确认提交
            </button>
          )}
          {canCleanup && (
            <button className="button secondary" disabled={!!busy} onClick={onCleanup}>
              {busy === "cleanup" ? <Loader2 size={16} className="spin" /> : <Trash2 size={16} />}
              清理来源分支
            </button>
          )}
          {canAbort && (
            <button className="button danger" disabled={!!busy} onClick={onAbort}>
              {busy === "abort" ? <Loader2 size={16} className="spin" /> : <XCircle size={16} />}
              中止
            </button>
          )}
          {canDelete && (
            <button
              className="button ghost dangerText"
              disabled={!!busy}
              onClick={() => {
                if (window.confirm("删除这张集成单？这会清理它自己的 integration worktree 和临时分支，但不会删除来源 fix/* 分支。")) {
                  onDelete();
                }
              }}
            >
              {busy === "delete" ? <Loader2 size={16} className="spin" /> : <Trash2 size={16} />}
              删除集成单
            </button>
          )}
        </div>
      </div>

      {/* Info */}
      <div className="intDetailInfo">
        <div className="intInfoRow">
          <span className="intInfoLabel">目标分支</span>
          <code>{run.target_branch}</code>
        </div>
        <div className="intInfoRow">
          <span className="intInfoLabel">集成分支</span>
          <code>{run.integration_branch}</code>
        </div>
        {run.final_commit && (
          <div className="intInfoRow">
            <span className="intInfoLabel">Final Commit</span>
            <code>{run.final_commit.slice(0, 12)}</code>
          </div>
        )}
        <div className="intInfoRow">
          <span className="intInfoLabel">创建时间</span>
          <span>{run.created_at}</span>
        </div>
      </div>

      {/* Items Table */}
      <div className="intItemsSection">
        <h4>来源分支 ({run.items.length})</h4>
        <table className="intItemsTable">
          <thead>
            <tr>
              <th>分支</th>
              <th>方式</th>
              <th>状态</th>
              <th>错误</th>
            </tr>
          </thead>
          <tbody>
            {run.items.map(item => {
              const itemInfo = ITEM_STATUS_LABELS[item.status] ?? { text: item.status, cls: "gray" };
              return (
                <tr key={item.branch}>
                  <td><code className="intBranchCode">{item.branch}</code></td>
                  <td>{item.apply_method || "—"}</td>
                  <td><span className={`intItemBadge ${itemInfo.cls}`}>{itemInfo.text}</span></td>
                  <td className="intErrorCell">{item.error || "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* AI Review */}
      {run.ai_review.summary && (
        <div className="intAiSection">
          <h4>AI 复核</h4>
          <p>{run.ai_review.summary}</p>
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
