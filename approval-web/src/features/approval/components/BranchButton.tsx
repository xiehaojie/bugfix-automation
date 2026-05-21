import type { FixItem, FixValidationStatus } from "../types";
import { phaseLabel, taskHeadline } from "../taskText";

const VALIDATION_LABELS: Partial<Record<FixValidationStatus, string>> = {
  verifying: "预演中",
  "ready-to-commit": "可提交",
  committed: "已提交",
  reverted: "已撤回",
  conflict: "冲突",
  "verify-failed": "预演失败",
  cleaned: "已清理"
};

interface BranchButtonProps {
  item: FixItem;
  active: boolean;
  validationStatus?: FixValidationStatus;
  onClick: () => void;
}

export function BranchButton({ item, active, validationStatus, onClick }: BranchButtonProps) {
  const status = item.active ? "running" : item.pending ? "pending" : "done";
  const validationLabel = validationStatus ? VALIDATION_LABELS[validationStatus] : "";
  return (
    <button className={`branchButton ${status} ${active ? "active" : ""}`} onClick={onClick}>
      <span className={`statusDot ${validationStatus ?? status}`} />
      <div className="branchCopy">
        <strong>{item.branch.replace("fix/", "")}</strong>
        <small>{taskHeadline(item)}</small>
      </div>
      <span className="branchMeta">{validationLabel || (item.active ? phaseLabel(item.task_phase) : `${item.changed_files.length} 个改动文件`)}</span>
    </button>
  );
}
