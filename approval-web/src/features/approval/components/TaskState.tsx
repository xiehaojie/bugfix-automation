import type { FixItem } from "../types";
import { taskHeadline, taskSubtext, taskTone } from "../taskText";

export function TaskState({ item }: { item: FixItem }) {
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
