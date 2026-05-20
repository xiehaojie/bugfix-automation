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
    <div className="excelTableWrap">
      <table className="excelTable">
        <thead>
          <tr>
            <th>编号</th>
            <th>来源 / 分类</th>
            <th>状态</th>
            <th>问题描述</th>
            <th>备注</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {bugs.map(bug => (
            <tr key={`${bug.issue_id}-${bug.excel_row}`} className={bug.active ? "isActive" : ""}>
              <td>
                <div className="issueCell">
                  <strong>{bug.issue_id}</strong>
                  <small>行 {bug.excel_row}</small>
                  <ScreenshotCell bug={bug} />
                </div>
              </td>
              <td>
                <div className="sourceCell">
                  <span>{bug.source_system || "未知来源"}</span>
                  <small>{bug.primary_category || "未填"} / {bug.secondary_category || "未填"}</small>
                </div>
              </td>
              <td><StatusCell bug={bug} /></td>
              <td><div className="descriptionCell"><span>{bug.description || "未填写问题描述"}</span><small>{bug.branch}</small></div></td>
              <td><div className="remarkCell"><span>{bug.remark || "无"}</span>{bug.remark2 ? <small>{bug.remark2}</small> : null}</div></td>
              <td>
                <div className="rowActions">
                  <button className="iconTextButton accentLite" disabled={bug.active || Boolean(busyAction)} onClick={() => onPreview(bug)}>
                    <Eye size={14} />
                    预览
                  </button>
                  <button className="iconTextButton primaryLite" disabled={bug.active || Boolean(busyAction) || noWorkspace} title={noWorkspace ? "请先配置工作区" : undefined} onClick={() => void onRun(bug)}>
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
