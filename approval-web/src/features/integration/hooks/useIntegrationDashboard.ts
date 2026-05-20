import { useCallback, useEffect, useState } from "react";
import {
  abortIntegrationRun,
  cleanupIntegrationRun,
  confirmIntegrationRun,
  createIntegrationRun,
  deleteIntegrationRun,
  fetchAvailableBranches,
  fetchIntegrationDiff,
  fetchIntegrationRun,
  fetchIntegrationRuns,
  fetchTargetBranches,
  startIntegrationRun,
} from "../api";
import type { AvailableBranch, IntegrationRun } from "../types";

export function useIntegrationDashboard() {
  const [runs, setRuns] = useState<IntegrationRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string>("");
  const [selectedRun, setSelectedRun] = useState<IntegrationRun | null>(null);
  const [diff, setDiff] = useState("");
  const [availableBranches, setAvailableBranches] = useState<AvailableBranch[]>([]);
  const [targetBranches, setTargetBranches] = useState<string[]>([]);
  const [defaultTargetBranch, setDefaultTargetBranch] = useState("");
  const [workspaceId, setWorkspaceId] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [toast, setToast] = useState("");

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(""), 3000);
  };

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [nextRuns, nextBranches, nextTargets] = await Promise.all([
        fetchIntegrationRuns(),
        fetchAvailableBranches(),
        fetchTargetBranches(),
      ]);
      setRuns(nextRuns);
      setAvailableBranches(nextBranches);
      setTargetBranches(nextTargets.branches);
      setDefaultTargetBranch(nextTargets.current);
      setWorkspaceId(nextTargets.workspace_id);
    } catch (err) {
      showToast(`加载失败: ${err}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  // Load detail when selectedRunId changes
  useEffect(() => {
    if (!selectedRunId) {
      setSelectedRun(null);
      setDiff("");
      return;
    }
    let alive = true;
    (async () => {
      try {
        const [run, runDiff] = await Promise.all([
          fetchIntegrationRun(selectedRunId),
          fetchIntegrationDiff(selectedRunId),
        ]);
        if (alive) {
          setSelectedRun(run);
          setDiff(runDiff);
        }
      } catch (err) {
        if (alive) showToast(`加载详情失败: ${err}`);
      }
    })();
    return () => { alive = false; };
  }, [selectedRunId]);

  const doCreate = async (workspaceId: string, targetBranch: string, branches: string[]) => {
    setBusy("create");
    try {
      const run = await createIntegrationRun(workspaceId, targetBranch, branches);
      showToast(`集成单已创建: ${run.run_id}`);
      setSelectedRunId(run.run_id);
      await refresh();
    } catch (err) {
      showToast(`创建失败: ${err}`);
    } finally {
      setBusy("");
    }
  };

  const doStart = async () => {
    if (!selectedRunId) return;
    setBusy("start");
    try {
      const run = await startIntegrationRun(selectedRunId);
      setSelectedRun(run);
      showToast(`集成完成: ${run.status}`);
      const runDiff = await fetchIntegrationDiff(selectedRunId);
      setDiff(runDiff);
      await refresh();
    } catch (err) {
      showToast(`开始失败: ${err}`);
    } finally {
      setBusy("");
    }
  };

  const doConfirm = async () => {
    if (!selectedRunId) return;
    setBusy("confirm");
    try {
      const run = await confirmIntegrationRun(selectedRunId);
      setSelectedRun(run);
      showToast(`已确认提交: ${run.final_commit?.slice(0, 7)}`);
      await refresh();
    } catch (err) {
      showToast(`确认失败: ${err}`);
    } finally {
      setBusy("");
    }
  };

  const doCleanup = async () => {
    if (!selectedRunId) return;
    setBusy("cleanup");
    try {
      const run = await cleanupIntegrationRun(selectedRunId);
      setSelectedRun(run);
      showToast(`已清理 ${run.cleaned_branches?.length ?? 0} 个来源分支`);
      await refresh();
    } catch (err) {
      showToast(`清理失败: ${err}`);
    } finally {
      setBusy("");
    }
  };

  const doAbort = async () => {
    if (!selectedRunId) return;
    setBusy("abort");
    try {
      const run = await abortIntegrationRun(selectedRunId);
      setSelectedRun(run);
      showToast("已中止集成单");
      await refresh();
    } catch (err) {
      showToast(`中止失败: ${err}`);
    } finally {
      setBusy("");
    }
  };

  const doDelete = async () => {
    if (!selectedRunId) return;
    const runId = selectedRunId;
    setBusy("delete");
    try {
      await deleteIntegrationRun(runId);
      setSelectedRunId("");
      setSelectedRun(null);
      setDiff("");
      showToast(`已删除集成单: ${runId}`);
      await refresh();
    } catch (err) {
      showToast(`删除失败: ${err}`);
    } finally {
      setBusy("");
    }
  };

  return {
    runs,
    selectedRun,
    selectedRunId,
    setSelectedRunId,
    diff,
    availableBranches,
    targetBranches,
    defaultTargetBranch,
    workspaceId,
    loading,
    busy,
    toast,
    refresh,
    doCreate,
    doStart,
    doConfirm,
    doCleanup,
    doAbort,
    doDelete,
  };
}
