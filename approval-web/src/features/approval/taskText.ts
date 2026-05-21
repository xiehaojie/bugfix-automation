import type { TaskLike } from "./types";

export function taskHeadline(item: TaskLike) {
  if (item.active) return "Codex 正在执行";
  if (item.task_status === "pending-approval") return "Codex 已完成，等待你审批";
  if (item.task_status === "failed") return "执行失败，需要重新触发";
  if (item.task_status === "no-change") return "Codex 已结束，没有产出前端改动";
  if (item.task_status === "skipped") return "任务已跳过";
  if (item.pending) return "等待你审批";
  return "当前空闲";
}

export function taskSubtext(item: TaskLike) {
  if (item.active) {
    return `${phaseLabel(item.task_phase)}${item.task_detail ? ` · ${item.task_detail}` : ""}`;
  }
  if (item.task_status === "pending-approval") return item.task_detail || "可以先看代码比对，再决定是否通过或重新修改。";
  if (item.task_status === "failed") return item.task_detail || "请打开 Codex 日志，查看失败原因。";
  if (item.task_status === "no-change") return item.task_detail || "Codex 跑完了，但没有生成可提交的前端改动。";
  if (item.task_status === "skipped") return item.task_detail || "这个任务被系统跳过了。";
  return item.pending ? "还在待审批队列里。" : "当前没有需要处理的任务。";
}

export function taskTone(item: TaskLike) {
  if (item.active) return "running";
  if (item.task_status === "failed") return "failed";
  if (item.task_status === "pending-approval") return "pending";
  return "clean";
}

export function phaseLabel(phase: string) {
  if (phase === "prepare") return "正在准备 worktree";
  if (phase === "codex") return "Codex 正在分析并修改";
  if (phase === "verify") return "正在生成提交预演";
  if (phase === "done") return "已结束";
  if (phase === "queued") return "正在排队";
  if (phase === "failed") return "执行失败";
  if (phase === "reworking") return "正在根据补充信息重新修改";
  return "处理中";
}
