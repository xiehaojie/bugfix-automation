import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { fetchJson } from "../api";
import type { BugItem, CommitLocation, ConfigPayload, DashboardPayload, FixValidation, LogPayload, SchedulerPayload } from "../types";
import { formatBytes } from "../../../lib/format";
import { splitLines } from "../../../lib/splitLines";
import { useAutoRefresh } from "./useAutoRefresh";
import { useLogPolling } from "./useLogPolling";

export function useApprovalDashboard() {
  const [payload, setPayload] = useState<DashboardPayload>({ pending_count: 0, items: [] });
  const [bugs, setBugs] = useState<BugItem[]>([]);
  const [scheduler, setScheduler] = useState<SchedulerPayload | null>(null);
  const [config, setConfig] = useState<ConfigPayload | null>(null);
  const [selectedBranch, setSelectedBranch] = useState("");
  const [loading, setLoading] = useState(true);
  const [busyAction, setBusyAction] = useState("");
  const [toast, setToast] = useState("");
  const [schedulerHour, setSchedulerHour] = useState("22");
  const [schedulerMinute, setSchedulerMinute] = useState("0");
  const [excelFile, setExcelFile] = useState<File | null>(null);
  const [excelPathInput, setExcelPathInput] = useState("/Users/xiehaojie/Desktop/亦城数智人在线清单.xlsx");
  const [logPayload, setLogPayload] = useState<LogPayload>({ branch: "", path: "", content: "" });
  const [promptFields, setPromptFields] = useState("");
  const [promptContextPaths, setPromptContextPaths] = useState("");
  const [promptTemplate, setPromptTemplate] = useState("");
  const [maxConcurrency, setMaxConcurrency] = useState("2");
  const [branchSummaryFields, setBranchSummaryFields] = useState("");
  const [cliTool, setCliTool] = useState("codex");
  const [fixValidation, setFixValidation] = useState<FixValidation | null>(null);
  const [commitLocation, setCommitLocation] = useState<CommitLocation>("integration");
  const [verifyLog, setVerifyLog] = useState("");
  const [verifyCommands, setVerifyCommands] = useState("");
  const selectedBranchRef = useRef("");

  const selected = useMemo(
    () => payload.items.find(item => item.branch === selectedBranch) ?? payload.items[0],
    [payload.items, selectedBranch]
  );
  const selectedWorkspace = config?.workspaces.find(workspace => workspace.id === config.active_workspace);
  const actionDisabled = Boolean(busyAction) || !selected;

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [nextPayload, nextBugsPayload, nextConfig, nextScheduler] = await Promise.all([
        fetchJson<DashboardPayload>("/api/items"),
        fetchJson<{ bugs: BugItem[] }>("/api/bugs"),
        fetchJson<ConfigPayload>("/api/config"),
        fetchJson<SchedulerPayload>("/api/scheduler")
      ]);
      setPayload(nextPayload);
      setBugs(nextBugsPayload.bugs ?? []);
      setConfig(nextConfig);
      setScheduler(nextScheduler);
      setSelectedBranch(current => {
        if (current && nextPayload.items.some(item => item.branch === current)) return current;
        return nextPayload.items[0]?.branch ?? "";
      });
      setToast(current => current.includes("失败 (") ? "" : current);
    } catch (error) {
      setToast(error instanceof Error ? error.message : "刷新失败");
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshLog = useCallback(async (branch: string) => {
    if (!branch) {
      setLogPayload({ branch: "", path: "", content: "" });
      return;
    }
    setLogPayload(await fetchJson<LogPayload>(`/api/logs?branch=${encodeURIComponent(branch)}`));
  }, []);

  const refreshVerifyLog = useCallback(async (branch: string) => {
    if (!branch) { setVerifyLog(""); return; }
    try {
      const data = await fetchJson<{ ok: boolean; content: string }>(`/api/fix-validations/${encodeURIComponent(branch)}/verify-log`);
      if (selectedBranchRef.current === branch) setVerifyLog(data.content ?? "");
    } catch {
      setVerifyLog("");
    }
  }, []);

  const refreshFixValidation = useCallback(async (branch: string) => {
    if (!branch) {
      setFixValidation(null);
      return;
    }
    try {
      const data = await fetchJson<{ validation: FixValidation }>(`/api/fix-validations/${encodeURIComponent(branch)}`);
      if (data.validation.branch !== branch || selectedBranchRef.current !== branch) return;
      setFixValidation(data.validation);
      if (data.validation.final_commit_location === "integration" || data.validation.final_commit_location === "target") {
        setCommitLocation(data.validation.final_commit_location);
      }
    } catch (error) {
      setFixValidation(null);
      setToast(error instanceof Error ? error.message : "验证状态刷新失败");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useAutoRefresh(refresh);
  useLogPolling(selected?.branch, setLogPayload, refreshLog, config?.api_port);

  useEffect(() => {
    if (!scheduler) return;
    setSchedulerHour(String(scheduler.schedule_hour));
    setSchedulerMinute(String(scheduler.schedule_minute));
  }, [scheduler?.schedule_hour, scheduler?.schedule_minute]);

  useEffect(() => {
    if (!config) return;
    setBranchSummaryFields((config.branch_summary_fields ?? []).join("\n"));
    setPromptFields(config.prompt.fields.join("\n"));
    setPromptContextPaths(config.prompt.context_paths.join("\n"));
    setPromptTemplate(config.prompt.template);
    setMaxConcurrency(String(config.max_concurrency));
    setCliTool(config.cli_tool || "codex");
    const ws = config.workspaces.find(w => w.id === config.active_workspace);
    if (ws) setVerifyCommands((ws.verify_commands ?? []).join("\n"));
  }, [config]);

  useEffect(() => {
    const branch = selected?.branch ?? "";
    selectedBranchRef.current = branch;
    setFixValidation(null);
    setVerifyLog("");
    void refreshLog(branch);
    void refreshFixValidation(branch);
    void refreshVerifyLog(branch);
  }, [refreshFixValidation, refreshLog, refreshVerifyLog, selected?.branch]);

  const switchWorkspace = useCallback(async (workspaceId: string) => {
    if (!config || workspaceId === config.active_workspace) return;
    const prevConfig = config;
    const ws = config.workspaces.find(w => w.id === workspaceId);
    if (!ws) return;
    // Optimistic: update header instantly
    setConfig({
      ...config,
      active_workspace: workspaceId,
      target_repo: ws.target_repo,
      target_app_path: ws.target_app_path,
      prompt: { ...config.prompt, context_paths: ws.prompt_context_paths },
    });
    setVerifyCommands((ws.verify_commands ?? []).join("\n"));
    setBusyAction("switch-workspace");
    try {
      await fetchJson("/api/workspace/select", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workspace_id: workspaceId }),
      });
      setToast("工作区已切换");
      await refresh();
    } catch (error) {
      setConfig(prevConfig);
      setToast(error instanceof Error ? error.message : "切换失败");
    } finally {
      setBusyAction("");
    }
  }, [config, refresh]);

  const postAction = async (path: string, body: Record<string, unknown>, success: string) => {
    setBusyAction(path);
    setToast("");
    try {
      const data = await fetchJson<{ ok?: boolean }>(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      });
      if (data.ok === false) throw new Error("操作失败");
      setToast(success);
      await refresh();
      if (selected?.branch) {
        await refreshLog(selected.branch);
        await refreshFixValidation(selected.branch);
      }
    } catch (error) {
      setToast(error instanceof Error ? error.message : "操作失败");
    } finally {
      setBusyAction("");
    }
  };

  const postFixValidationAction = async (action: "verify" | "commit" | "revert" | "undo-commit" | "remove-preview" | "cleanup-source", success: string, body: Record<string, unknown> = {}) => {
    if (!selected?.branch) return;
    setBusyAction(`fix-validation:${action}`);
    setToast("");
    try {
      const data = await fetchJson<{ validation: FixValidation }>(`/api/fix-validations/${encodeURIComponent(selected.branch)}/${action}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      });
      if (data.validation.branch === selectedBranchRef.current) {
        setFixValidation(data.validation);
      }
      setToast(success);
      await refresh();
      await refreshLog(selected.branch);
      await refreshFixValidation(selected.branch);
      await refreshVerifyLog(selected.branch);
    } catch (error) {
      setToast(error instanceof Error ? error.message : "操作失败");
    } finally {
      setBusyAction("");
    }
  };

  const uploadExcel = async (file?: File | null) => {
    const target = file ?? excelFile;
    if (!target) {
      setToast("请先选择一个 .xlsx 文件");
      return;
    }
    const form = new FormData();
    form.append("file", target);
    setBusyAction("/api/excel/upload");
    setToast("");
    try {
      const data = await fetchJson<{ ok?: boolean; excel_path: string; file?: ConfigPayload["excel_file"] }>("/api/excel/upload", { method: "POST", body: form });
      if (data.ok === false) throw new Error("上传失败");
      setToast(`已上传并切换：${target.name}，${formatBytes(data.file?.size)}`);
      setExcelFile(null);
      await refresh();
    } catch (error) {
      setToast(error instanceof Error ? error.message : "上传失败");
    } finally {
      setBusyAction("");
    }
  };

  const selectExcelPath = async () => {
    if (!excelPathInput.trim()) {
      setToast("请输入本机 xlsx 文件路径");
      return;
    }
    await postAction("/api/excel/select-path", { path: excelPathInput.trim() }, "已切换到本机 Excel 路径");
  };

  const runBug = async (bug: BugItem) => {
    setBusyAction(`run-${bug.excel_row}`);
    setToast("");
    try {
      const data = await fetchJson<{ ok?: boolean; branch: string; status: string }>(`/api/bugs/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ excel_row: bug.excel_row })
      });
      if (data.ok === false) throw new Error("执行失败");
      setSelectedBranch(data.branch || bug.branch);
      setToast(`已开始执行：${bug.branch}`);
      await refresh();
      await refreshLog(data.branch || bug.branch);
    } catch (error) {
      setToast(error instanceof Error ? error.message : "执行失败");
    } finally {
      setBusyAction("");
    }
  };

  const deleteBug = async (bug: BugItem) => {
    setBusyAction(`delete-${bug.excel_row}`);
    setToast("");
    try {
      const data = await fetchJson<{ ok?: boolean; branch: string }>(`/api/bugs/delete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ excel_row: bug.excel_row })
      });
      if (data.ok === false) throw new Error("删除失败");
      setToast(`已删除：${bug.branch}`);
      await refresh();
      if (selected?.branch === data.branch) {
        setSelectedBranch("");
        await refreshLog("");
      }
    } catch (error) {
      setToast(error instanceof Error ? error.message : "删除失败");
    } finally {
      setBusyAction("");
    }
  };

  const installSchedule = () => {
    const hour = Number(schedulerHour);
    const minute = Number(schedulerMinute);
    if (!Number.isInteger(hour) || hour < 0 || hour > 23 || !Number.isInteger(minute) || minute < 0 || minute > 59) {
      setToast("任务时间必须是 00:00 到 23:59");
      return;
    }
    void postAction("/api/scheduler/install", { hour, minute }, "定时任务已开启/更新");
  };

  const saveAutomationConfig = () => {
    const concurrency = Number(maxConcurrency);
    if (!Number.isInteger(concurrency) || concurrency < 1 || concurrency > 8) {
      setToast("最高并发数必须在 1-8 之间");
      return;
    }
    void postAction(
      "/api/config/update",
      {
        max_concurrency: concurrency,
        cli_tool: cliTool.trim() || "codex",
        branch_summary_fields: splitLines(branchSummaryFields),
        prompt: {
          fields: splitLines(promptFields),
          template: promptTemplate,
          context_paths: splitLines(promptContextPaths)
        }
      },
      "配置已保存"
    );
  };

  return {
    actionDisabled,
    branchSummaryFields,
    bugs,
    busyAction,
    cliTool,
    config,
    commitLocation,
    deleteBug,
    excelFile,
    excelPathInput,
    fixValidation,
    installSchedule,
    loading,
    logPayload,
    maxConcurrency,
    payload,
    postAction,
    postFixValidationAction,
    promptContextPaths,
    promptFields,
    promptTemplate,
    refresh,
    runBug,
    saveAutomationConfig,
    switchWorkspace,
    scheduler,
    schedulerHour,
    schedulerMinute,
    selectExcelPath,
    selected,
    selectedWorkspace,
    setBranchSummaryFields,
    setCliTool,
    setCommitLocation,
    setExcelFile,
    setExcelPathInput,
    setMaxConcurrency,
    setPromptContextPaths,
    setPromptFields,
    setPromptTemplate,
    setSchedulerHour,
    setSchedulerMinute,
    setSelectedBranch,
    toast,
    uploadExcel,
    verifyCommands,
    setVerifyCommands,
    verifyLog
  };
}
