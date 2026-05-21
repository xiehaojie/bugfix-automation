"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { BotMessageSquare, CheckCircle2, Clock3, FileDiff, GitBranch, History, RefreshCcwDot, XCircle } from "lucide-react";
import { fetchJson } from "../api";
import type { HistoryDetailPayload, HistoryOperation, HistoryOperationsPayload, HistoryStats } from "../types";
import LogPane from "./LogPane";

const KIND_LABELS: Record<string, string> = {
  run_one: "单条执行",
  run_once: "批量执行",
  "fix-preview": "提交预演",
  "fix-commit": "提交修复",
  "fix-approve": "审批提交",
  "fix-reject": "拒绝删除",
  "fix-rework": "继续修改",
  "fix-revert": "撤回提交",
  "fix-undo-commit": "撤销提交",
  "fix-remove-preview": "移除预演",
  "fix-cleanup-source": "清理来源",
};

type OperationHistoryPanelProps = {
  onOpenBranch?: (branch: string) => void;
};

export function OperationHistoryPanel({ onOpenBranch }: OperationHistoryPanelProps) {
  const [payload, setPayload] = useState<HistoryOperationsPayload>({ items: [], stats: emptyStats() });
  const [selectedId, setSelectedId] = useState("");
  const [detail, setDetail] = useState<HistoryDetailPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState("");

  const selected = useMemo(
    () => payload.items.find(item => item.id === selectedId) ?? payload.items[0] ?? null,
    [payload.items, selectedId],
  );

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const next = await fetchJson<HistoryOperationsPayload>("/api/history/operations?limit=200");
      setPayload(next);
      setSelectedId(current => current && next.items.some(item => item.id === current) ? current : next.items[0]?.id ?? "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "操作记录加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!selected?.id) {
      setDetail(null);
      return;
    }
    let alive = true;
    setDetailLoading(true);
    fetchJson<HistoryDetailPayload>(`/api/history/operations/${encodeURIComponent(selected.id)}`)
      .then(next => { if (alive) setDetail(next); })
      .catch(err => { if (alive) setError(err instanceof Error ? err.message : "记录详情加载失败"); })
      .finally(() => { if (alive) setDetailLoading(false); });
    return () => { alive = false; };
  }, [selected?.id]);

  return (
    <section className="historyPanel">
      <header className="historyHeader">
        <div className="historyTitle">
          <History size={18} />
          <div>
            <h2>操作记录</h2>
            <p>修复、提交、拒绝、重改和 AI 对话都会沉淀在这里。</p>
          </div>
        </div>
        <button className="button ghost" onClick={() => void refresh()} disabled={loading} title="刷新记录">
          <RefreshCcwDot size={15} className={loading ? "spin" : ""} />
        </button>
      </header>

      <div className="historyStats">
        <Stat label="总操作" value={payload.stats.total} />
        <Stat label="提交修复" value={payload.stats.submitted} tone="green" />
        <Stat label="拒绝删除" value={payload.stats.rejected} tone="red" />
        <Stat label="继续修改" value={payload.stats.reworked} />
        <Stat label="预演" value={payload.stats.previewed} />
        <Stat label="失败" value={payload.stats.failed} tone="red" />
      </div>

      {error ? <div className="historyError">{error}</div> : null}

      <div className="historyLayout">
        <div className="historyList" aria-busy={loading}>
          {payload.items.length === 0 && !loading ? (
            <div className="historyEmpty">暂无操作记录</div>
          ) : null}
          {payload.items.map(item => (
            <button
              className={`historyItem ${item.id === selected?.id ? "active" : ""}`}
              key={item.id}
              onClick={() => setSelectedId(item.id)}
            >
              <span className={`historyKindDot ${statusTone(item.status)}`} />
              <span className="historyItemBody">
                <strong>{KIND_LABELS[item.kind] ?? item.kind}</strong>
                <small>{item.summary_text || item.branch || item.id}</small>
                <code>{item.branch || "无分支"}</code>
              </span>
              <span className="historyTime">{formatTime(item.started_at)}</span>
            </button>
          ))}
        </div>

        <div className="historyDetail">
          {!selected ? (
            <div className="historyEmpty">选择一条记录查看详情</div>
          ) : (
            <>
              <div className="historyDetailTop">
                <div className="historyDetailTitle">
                  {statusTone(selected.status) === "red" ? <XCircle size={16} /> : <CheckCircle2 size={16} />}
                  <div>
                    <h3>{KIND_LABELS[selected.kind] ?? selected.kind}</h3>
                    <p>{selected.summary_text || selected.status}</p>
                  </div>
                </div>
                <div className="historyMetaGrid">
                  <Meta label="状态" value={selected.status} />
                  <Meta label="工作区" value={selected.workspace_id || "-"} />
                  <Meta label="Bug" value={selected.issue_id || "-"} />
                  <Meta label="Excel 行" value={selected.excel_row ? String(selected.excel_row) : "-"} />
                  <Meta label="开始" value={formatTime(selected.started_at)} />
                  <Meta label="结束" value={selected.ended_at ? formatTime(selected.ended_at) : "-"} />
                </div>
                {selected.branch ? (
                  <button className="buttonSmall ghost" onClick={() => onOpenBranch?.(selected.branch)}>
                    <GitBranch size={13} />
                    查看当前分支
                  </button>
                ) : null}
              </div>

              {detailLoading ? <div className="historyEmpty compact">详情加载中...</div> : null}

              <section className="historySection">
                <h4><Clock3 size={14} />事件时间线</h4>
                <div className="historyEvents">
                  {(detail?.events ?? []).length === 0 ? <span className="historyMuted">暂无事件</span> : null}
                  {(detail?.events ?? []).map(event => (
                    <div className="historyEvent" key={event.id}>
                      <span>{formatTime(event.created_at)}</span>
                      <strong>{event.status || event.event_type}</strong>
                      <p>{event.message || event.event_type}</p>
                    </div>
                  ))}
                </div>
              </section>

              <section className="historySection">
                <h4><FileDiff size={14} />修复改动预览</h4>
                {(detail?.changed_files ?? []).length > 0 ? (
                  <div className="historyFileList">
                    {detail?.changed_files.map(file => <code key={file}>{file}</code>)}
                  </div>
                ) : null}
                {detail?.diff_preview ? (
                  <pre className="historyDiffPreview">{detail.diff_preview}</pre>
                ) : (
                  <span className="historyMuted">这条记录没有可展示的 diff 预览</span>
                )}
              </section>

              <section className="historySection">
                <h4><BotMessageSquare size={14} />AI 对话预览</h4>
                {(detail?.ai_sessions ?? []).length === 0 ? <span className="historyMuted">这条记录没有绑定 AI 会话</span> : null}
                {(detail?.ai_sessions ?? []).map(session => (
                  <div className="historyAiSession" key={session.id}>
                    <div className="historyAiHeader">
                      <strong>{session.cli_tool}</strong>
                      <span>{session.status}</span>
                      <code>{session.log_path}</code>
                    </div>
                    {session.prompt_preview ? (
                      <details className="historyPrompt">
                        <summary>查看 Prompt 预览</summary>
                        <pre>{session.prompt_preview}</pre>
                      </details>
                    ) : null}
                    <LogPane content={session.log_preview} streaming={false} placeholder="暂无 AI 日志预览" />
                  </div>
                ))}
              </section>
            </>
          )}
        </div>
      </div>
    </section>
  );
}

function Stat({ label, value, tone = "blue" }: { label: string; value: number; tone?: "blue" | "green" | "red" }) {
  return (
    <div className={`historyStat ${tone}`}>
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div className="historyMeta">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function emptyStats(): HistoryStats {
  return { total: 0, runs: 0, submitted: 0, rejected: 0, reworked: 0, previewed: 0, failed: 0 };
}

function statusTone(status: string): "green" | "red" | "blue" {
  if (["failed", "conflict", "rejected"].includes(status)) return "red";
  if (["succeeded", "committed", "ready-to-commit", "preview-removed", "cleaned", "reverted"].includes(status)) return "green";
  return "blue";
}

function formatTime(value: string): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}
