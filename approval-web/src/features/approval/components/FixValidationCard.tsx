import { AlertTriangle, BadgeCheck, GitCommit, GitMerge, Info, Loader2, RotateCcw, Trash2, Undo2, XCircle } from "lucide-react";

import type { CommitLocation, FixItem, FixValidation } from "../types";

const STATUS_LABELS: Record<string, string> = {
  pending: "待合并验证",
  verifying: "合并验证中",
  "ready-to-commit": "可提交",
  committed: "已提交",
  reverted: "已撤回",
  conflict: "有合并冲突",
  "verify-failed": "测试失败",
  "ai-review-needed": "AI 建议复查",
  "preview-removed": "预演已移除",
  cleaned: "来源已清理"
};

/**
 * 每个状态下告诉用户发生了什么、目标分支是否受影响、以及下一步应该怎么做。
 */
const STATUS_NOTES: Record<string, string> = {
  pending:
    "点击「开始合并验证」，系统会把修复内容合并到一个临时集成分支，检查是否有冲突并运行测试。你的目标分支不会被改动。",
  verifying:
    "正在临时集成分支上检查冲突、运行测试，请稍候……你的目标分支不会被改动。",
  "ready-to-commit":
    "验证通过，目标分支暂未改动。选择提交位置后点击「提交此修复」，改动才会正式写入。",
  committed:
    "修复已提交。如有问题，可点击「撤回此提交」生成一个反向提交，将本次修复从目标分支中移除。",
  reverted:
    "本次修复已通过反向提交撤销，目标分支已恢复原样。",
  conflict:
    "修复内容与目标分支存在冲突，临时合并失败。你的目标分支和原始修复分支均未受影响。可点击「移除预演」让 AI 重新修复后再次验证。",
  "verify-failed":
    "测试运行在临时集成分支上，你的目标分支和原始修复分支均未受影响。可重新验证或点击「移除预演」让 AI 重新修复。",
  "ai-review-needed":
    "代码合并和测试均已通过，但 AI 复核发现潜在问题，建议先查看右侧 AI 分析，再决定是否提交。",
  "preview-removed":
    "预演已清除，原始修复分支保持不变，可重新触发合并验证。",
  cleaned:
    "来源修复分支已清理完毕。"
};

interface FixValidationCardProps {
  item: FixItem;
  validation: FixValidation | null;
  busyAction: string;
  actionDisabled: boolean;
  commitLocation: CommitLocation;
  verifyCommands: string;
  onVerifyCommandsChange: (value: string) => void;
  onCommitLocationChange: (location: CommitLocation) => void;
  onVerify: () => void;
  onCommit: () => void;
  onRevert: () => void;
  onUndoCommit: () => void;
  onRemovePreview: () => void;
  onReject: () => void;
  onCleanup: () => void;
}

export function FixValidationCard({
  item,
  validation,
  busyAction,
  actionDisabled,
  commitLocation,
  verifyCommands,
  onVerifyCommandsChange,
  onCommitLocationChange,
  onVerify,
  onCommit,
  onRevert,
  onUndoCommit,
  onRemovePreview,
  onReject,
  onCleanup
}: FixValidationCardProps) {
  const status = validation?.status ?? "pending";
  const isBusy = busyAction.startsWith("fix-validation:") || busyAction === "/api/reject";
  const verifyStatus = validation?.verify?.status || "未运行";
  const changedCount = validation?.changed_files.length ?? item.changed_files.length;

  // ── 每个状态下展示哪些按钮 ──────────────────────────────────────
  // 只展示当前状态下有意义的操作，避免用户看到一堆灰色按钮不知所措。
  const showVerify    = !["verifying", "committed", "reverted", "cleaned"].includes(status);
  const showCommit    = ["ready-to-commit", "ai-review-needed"].includes(status);
  const showRevert    = status === "committed";
  const showRemove    = ["ready-to-commit", "conflict", "verify-failed", "ai-review-needed"].includes(status);
  const showCleanup   = status === "committed" || status === "reverted";
  const showReject    = !["committed", "reverted", "cleaned"].includes(status);

  return (
    <section className={`fixValidationCard ${status}`}>
      <div className="fixValidationHeader">
        <div>
          <span className="fixValidationEyebrow"><GitMerge size={13} /> 单 Bug 自动合并验证</span>
          <h3>{STATUS_LABELS[status] ?? status}</h3>
        </div>
        <span className={`fixValidationBadge ${status}`}>{STATUS_LABELS[status] ?? status}</span>
      </div>

      {/* 状态说明：告诉用户发生了什么以及下一步怎么做 */}
      {STATUS_NOTES[status] ? (
        <div className={`fixValidationNote ${["conflict", "verify-failed"].includes(status) ? "warn" : ""}`}>
          {["conflict", "verify-failed"].includes(status)
            ? <AlertTriangle size={13} />
            : <Info size={13} />}
          {STATUS_NOTES[status]}
        </div>
      ) : null}

      <div className="fixValidationStats">
        <span>集成分支 <strong title="系统创建的临时合并分支，用于测试，不影响目标分支">{validation?.integration_branch || "待创建"}</strong></span>
        <span>测试结果 <strong>{verifyStatus}</strong></span>
        <span>改动文件 <strong>{changedCount}</strong></span>
      </div>

      {validation?.error ? (
        <div className="fixValidationError"><AlertTriangle size={14} />{validation.error}</div>
      ) : null}

      {/* 失败命令详情：直接内联展示错误日志，不用再去别处找 */}
      {["verify-failed", "conflict"].includes(status) && validation?.verify?.commands?.length ? (
        <div className="fixValidationCmdList">
          {validation.verify.commands.map((cmd, i) => (
            <div key={i} className={`fixValidationCmd ${cmd.status}`}>
              <div className="fixValidationCmdHeader">
                <span className={`fixValidationCmdStatus ${cmd.status}`}>
                  {cmd.status === "passed" ? "✓" : cmd.status === "failed" ? "✗" : cmd.status === "timeout" ? "⏱" : "!"}
                </span>
                <code className="fixValidationCmdName">{cmd.command}</code>
              </div>
              {cmd.log_tail && cmd.status !== "passed" ? (
                <pre className="fixValidationCmdLog">{cmd.log_tail}</pre>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}

      {showCommit ? (
        <fieldset className="commitLocationBox">
          <legend>选择提交位置（改动写入哪里）</legend>
          <label className={commitLocation === "integration" ? "active" : ""}>
            <input type="radio" name="commitLocation" checked={commitLocation === "integration"} onChange={() => onCommitLocationChange("integration")} />
            <span>仅写入临时集成分支</span>
            <small>更安全，目标分支暂时不变，可随时撤回</small>
          </label>
          <label className={commitLocation === "target" ? "active" : ""}>
            <input type="radio" name="commitLocation" checked={commitLocation === "target"} onChange={() => onCommitLocationChange("target")} />
            <span>直接写入目标分支 {validation?.target_branch || "main"}</span>
            <small>改动立即生效，可用「撤回此提交」生成反向提交撤销</small>
          </label>
        </fieldset>
      ) : null}

      {/* 主操作区：按当前状态只显示相关按钮 */}
      <div className="fixValidationActions">
        {showVerify && (
          <div className="fixVerifyCommandsRow">
            <label className="fixVerifyCommandsLabel">验证命令（每行一条，留空则跳过验证）</label>
            <textarea
              className="fixVerifyCommandsInput"
              value={verifyCommands}
              onChange={e => onVerifyCommandsChange(e.target.value)}
              rows={2}
              placeholder={"npm run build\nnpm run lint --fix"}
            />
          </div>
        )}
        {showVerify && (
          <button
            className="button primary"
            disabled={actionDisabled || item.active || isBusy}
            onClick={onVerify}
            title={status === "pending"
              ? "在临时集成分支上检查冲突并运行测试，不改动目标分支"
              : "清除上次验证结果，重新在临时集成分支上检查并测试"}
          >
            {busyAction === "fix-validation:verify" ? <Loader2 size={16} className="spin" /> : <GitMerge size={16} />}
            {status === "pending" ? "开始合并验证" : "重新验证"}
          </button>
        )}

        {showCommit && (
          <button
            className="button secondary"
            disabled={actionDisabled || isBusy}
            onClick={onCommit}
            title={commitLocation === "target"
              ? `将验证后的改动提交到目标分支 ${validation?.target_branch || "main"}`
              : "将验证后的改动提交到临时集成分支，目标分支暂不变动"}
          >
            {busyAction === "fix-validation:commit" ? <Loader2 size={16} className="spin" /> : <GitCommit size={16} />}
            提交此修复
          </button>
        )}

        {showRevert && (
          <button
            className="button ghost"
            disabled={actionDisabled || isBusy}
            onClick={onUndoCommit}
            title="撤销上次提交（git reset --soft），直接移除 commit，改动保留在暂存区。仅当该提交是最新一次时可用。"
          >
            {busyAction === "fix-validation:undo-commit" ? <Loader2 size={16} className="spin" /> : <Undo2 size={16} />}
            撤销上次提交
          </button>
        )}
        {showRevert && (
          <button
            className="button ghost"
            disabled={actionDisabled || isBusy}
            onClick={onRevert}
            title="生成一个反向提交来撤销本次修复，不会删除或重写历史"
          >
            {busyAction === "fix-validation:revert" ? <Loader2 size={16} className="spin" /> : <RotateCcw size={16} />}
            撤回此提交(revert)
          </button>
        )}

        {showRemove && (
          <button
            className="button ghost"
            disabled={actionDisabled || isBusy}
            onClick={onRemovePreview}
            title="删除临时集成分支，原始修复分支保持不变，可重新触发验证"
          >
            {busyAction === "fix-validation:remove-preview" ? <Loader2 size={16} className="spin" /> : <Trash2 size={16} />}
            移除预演
          </button>
        )}

        {showCleanup && (
          <button
            className="button ghost"
            disabled={actionDisabled || isBusy}
            onClick={onCleanup}
            title="删除本地 fix/* 修复分支和对应 worktree（修复已提交后的清理操作）"
          >
            {busyAction === "fix-validation:cleanup-source" ? <Loader2 size={16} className="spin" /> : <BadgeCheck size={16} />}
            清理修复分支
          </button>
        )}

        {showReject && (
          <button
            className="button danger"
            disabled={actionDisabled || item.active || isBusy}
            onClick={onReject}
            title="拒绝本条修复，删除对应的 fix/* 分支，此操作不可恢复"
          >
            <XCircle size={16} />
            拒绝并删除
          </button>
        )}
      </div>
    </section>
  );
}
