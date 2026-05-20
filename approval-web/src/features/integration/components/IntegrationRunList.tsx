"use client";

import type { IntegrationRun } from "../types";

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

interface ListProps {
  runs: IntegrationRun[];
  selectedRunId: string;
  onSelect: (runId: string) => void;
}

export function IntegrationRunList({ runs, selectedRunId, onSelect }: ListProps) {
  if (runs.length === 0) {
    return <div className="intEmpty">暂无集成单，点击上方"创建集成单"开始。</div>;
  }

  return (
    <div className="intRunList">
      {runs.map(run => {
        const statusInfo = STATUS_LABELS[run.status] ?? { text: run.status, tone: "gray" };
        const appliedCount = run.items.filter(i => i.status === "applied").length;
        return (
          <button
            key={run.run_id}
            className={`intRunCard ${selectedRunId === run.run_id ? "active" : ""}`}
            onClick={() => onSelect(run.run_id)}
          >
            <div className="intRunCardHeader">
              <span className={`intStatusBadge ${statusInfo.tone}`}>{statusInfo.text}</span>
              <span className="intRunTarget">→ {run.target_branch}</span>
            </div>
            <div className="intRunCardBody">
              <span className="intRunId">{run.run_id}</span>
              <span className="intRunMeta">{appliedCount}/{run.items.length} 分支</span>
            </div>
          </button>
        );
      })}
    </div>
  );
}
