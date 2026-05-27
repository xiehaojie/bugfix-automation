import { Eye, Loader2, PlayCircle, Trash2 } from "lucide-react";

import { Badge } from "../../../components/ui/Badge";
import { taskHeadline } from "../taskText";
import type { BugItem } from "../types";

export function BugTable({
  bugs,
  busyAction,
  noWorkspace = false,
  onRun,
  onDelete,
  onPreview
}: {
  bugs: BugItem[];
  busyAction: string;
  noWorkspace?: boolean;
  onRun: (bug: BugItem) => void | Promise<void>;
  onDelete: (bug: BugItem) => void | Promise<void>;
  onPreview: (bug: BugItem) => void;
}) {
  if (bugs.length === 0) return <div className="noDiff">当前 Excel 没有命中筛选规则的 bug。</div>;
  return (
    <div className="bugQueueList">
      {bugs.map(bug => (
        <article key={`${bug.issue_id}-${bug.excel_row}`} className={`bugQueueCard ${bug.active ? "active" : ""}`}>
          <header className="bugQueueCardHeader">
            <div className="bugQueueId">
              <strong>#{bug.issue_id}</strong>
              <span>Excel 行 {bug.excel_row}</span>
            </div>
            <Badge tone={bug.priority === "高" ? "blue" : "gray"}>{bug.priority || "未定级"}</Badge>
          </header>
          <div className="bugQueueTitle">{bug.description || "未填写问题描述"}</div>
          <div className="bugQueueMeta">
            <span>{bug.source_system || "未知来源"}</span>
            <span>{bug.primary_category || "未填"} / {bug.secondary_category || "未填"}</span>
          </div>
          <StatusCell bug={bug} />
          {bug.remark || bug.remark2 ? (
            <div className="bugQueueRemark">
              <span>{bug.remark || "无"}</span>
              {bug.remark2 ? <small>{bug.remark2}</small> : null}
            </div>
          ) : null}
          <div className="bugQueueFooter">
            <ScreenshotCell bug={bug} />
            <div className="rowActions">
              <button className="iconTextButton accentLite" disabled={bug.active || Boolean(busyAction)} onClick={() => onPreview(bug)} title="预览提示词">
                <Eye size={14} />
                预览
              </button>
              <button className="iconTextButton primaryLite" disabled={bug.active || Boolean(busyAction) || noWorkspace} title={noWorkspace ? "请先配置工作区" : "执行修复"} onClick={() => void onRun(bug)}>
                {busyAction === `run-${bug.excel_row}` ? <Loader2 size={14} className="spin" /> : <PlayCircle size={14} />}
                执行
              </button>
              <button className="iconTextButton dangerLite" disabled={bug.active || Boolean(busyAction)} onClick={() => void onDelete(bug)} title="从队列删除">
                {busyAction === `delete-${bug.excel_row}` ? <Loader2 size={14} className="spin" /> : <Trash2 size={14} />}
              </button>
            </div>
          </div>
          <div className="bugQueueTask">{taskHeadline(bug)}{bug.task_detail ? ` · ${bug.task_detail}` : ""}</div>
        </article>
      ))}
    </div>
  );
}

function StatusCell({ bug }: { bug: BugItem }) {
  return (
    <div className="statusStack">
      <div className="statusPair">
        <span className="statusLabel">提出人</span>
        <Badge>{bug.requester_status}</Badge>
      </div>
      <div className="statusPair">
        <span className="statusLabel">对接人</span>
        <Badge tone={bug.assignee_status ? "blue" : "gray"}>{bug.assignee_status || "未填"}</Badge>
      </div>
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
