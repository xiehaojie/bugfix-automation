"use client";

import { useState } from "react";
import { GitMerge, Loader2, Plus, RefreshCcwDot } from "lucide-react";
import { useIntegrationDashboard } from "../../src/features/integration/hooks/useIntegrationDashboard";
import { IntegrationCreateForm } from "../../src/features/integration/components/IntegrationCreateForm";
import { IntegrationRunList } from "../../src/features/integration/components/IntegrationRunList";
import { IntegrationDetail } from "../../src/features/integration/components/IntegrationDetail";
import Link from "next/link";

export default function IntegrationPage() {
  const {
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
  } = useIntegrationDashboard();

  const [showCreate, setShowCreate] = useState(false);

  return (
    <main className="consoleShell">
      <section className="mainStage">
        <header className="commandBar">
          <div className="commandBarLeft">
            <GitMerge size={18} className="commandBarIcon" />
            <h2 className="pageTitle">集成预演</h2>
            <Link href="/" className="navLink">← 返回审批台</Link>
          </div>
          <div className="commandActions">
            <button className="button ghost" onClick={() => void refresh()} disabled={loading} title="刷新">
              <RefreshCcwDot size={16} className={loading ? "spin" : ""} />
            </button>
            <button className="button secondary" onClick={() => setShowCreate(true)} disabled={!!busy}>
              <Plus size={16} />
              创建集成单
            </button>
          </div>
        </header>

        {toast && <div className="toast">{toast}</div>}

        {showCreate && (
          <IntegrationCreateForm
            availableBranches={availableBranches}
            targetBranches={targetBranches}
            defaultTargetBranch={defaultTargetBranch}
            workspaceId={workspaceId}
            busy={!!busy}
            onSubmit={(ws, branch, branches) => {
              void doCreate(ws, branch, branches);
              setShowCreate(false);
            }}
            onCancel={() => setShowCreate(false)}
          />
        )}

        <div className="intLayout">
          <aside className="intSidebar">
            <IntegrationRunList
              runs={runs}
              selectedRunId={selectedRunId}
              onSelect={setSelectedRunId}
            />
          </aside>
          <section className="intMain">
            {selectedRun ? (
              <IntegrationDetail
                run={selectedRun}
                diff={diff}
                busy={busy}
                onStart={doStart}
                onConfirm={doConfirm}
                onCleanup={doCleanup}
                onAbort={doAbort}
                onDelete={doDelete}
              />
            ) : (
              <div className="blankState">
                <GitMerge size={32} />
                <h2>选择或创建一个集成单</h2>
                <p>将多个 fix/* 分支批量合并到目标分支，先集成预演再确认提交。</p>
              </div>
            )}
          </section>
        </div>
      </section>
    </main>
  );
}
