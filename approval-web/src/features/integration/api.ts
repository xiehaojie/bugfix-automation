import { fetchJson } from "../approval/api";
import type { AvailableBranch, IntegrationRun, TargetBranches } from "./types";

export async function fetchIntegrationRuns(): Promise<IntegrationRun[]> {
  const data = await fetchJson<{ runs: IntegrationRun[] }>("/api/integration-runs");
  return data.runs;
}

export async function fetchIntegrationRun(runId: string): Promise<IntegrationRun> {
  const data = await fetchJson<{ run: IntegrationRun }>(`/api/integration-runs/${encodeURIComponent(runId)}`);
  return data.run;
}

export async function fetchIntegrationDiff(runId: string): Promise<string> {
  const data = await fetchJson<{ diff: string }>(`/api/integration-runs/${encodeURIComponent(runId)}/diff`);
  return data.diff;
}

export async function fetchAvailableBranches(): Promise<AvailableBranch[]> {
  const data = await fetchJson<{ branches: AvailableBranch[] }>("/api/integration-runs/branches");
  return data.branches;
}

export async function fetchTargetBranches(): Promise<TargetBranches> {
  return fetchJson<TargetBranches>("/api/integration-runs/target-branches");
}

export async function createIntegrationRun(
  workspaceId: string,
  targetBranch: string,
  branches: string[]
): Promise<IntegrationRun> {
  const data = await fetchJson<{ run: IntegrationRun }>("/api/integration-runs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ workspace_id: workspaceId, target_branch: targetBranch, branches }),
  });
  return data.run;
}

export async function startIntegrationRun(runId: string): Promise<IntegrationRun> {
  const data = await fetchJson<{ run: IntegrationRun }>(`/api/integration-runs/${encodeURIComponent(runId)}/start`, {
    method: "POST",
  });
  return data.run;
}

export async function confirmIntegrationRun(runId: string): Promise<IntegrationRun> {
  const data = await fetchJson<{ run: IntegrationRun }>(`/api/integration-runs/${encodeURIComponent(runId)}/confirm`, {
    method: "POST",
  });
  return data.run;
}

export async function cleanupIntegrationRun(runId: string): Promise<IntegrationRun> {
  const data = await fetchJson<{ run: IntegrationRun }>(`/api/integration-runs/${encodeURIComponent(runId)}/cleanup`, {
    method: "POST",
  });
  return data.run;
}

export async function abortIntegrationRun(runId: string): Promise<IntegrationRun> {
  const data = await fetchJson<{ run: IntegrationRun }>(`/api/integration-runs/${encodeURIComponent(runId)}/abort`, {
    method: "POST",
  });
  return data.run;
}

export async function deleteIntegrationRun(runId: string): Promise<void> {
  await fetchJson<{ ok: boolean; deleted: boolean; run_id: string }>(`/api/integration-runs/${encodeURIComponent(runId)}`, {
    method: "DELETE",
  });
}
