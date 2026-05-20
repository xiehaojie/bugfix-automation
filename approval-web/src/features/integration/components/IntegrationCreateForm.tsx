"use client";

import { useEffect, useState } from "react";
import type { AvailableBranch } from "../types";

interface CreateFormProps {
  availableBranches: AvailableBranch[];
  targetBranches: string[];
  defaultTargetBranch: string;
  workspaceId: string;
  busy: boolean;
  onSubmit: (workspaceId: string, targetBranch: string, branches: string[]) => void;
  onCancel: () => void;
}

export function IntegrationCreateForm({
  availableBranches,
  targetBranches,
  defaultTargetBranch,
  workspaceId,
  busy,
  onSubmit,
  onCancel,
}: CreateFormProps) {
  const [targetBranch, setTargetBranch] = useState(defaultTargetBranch);
  const [selectedBranches, setSelectedBranches] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!targetBranch && defaultTargetBranch) setTargetBranch(defaultTargetBranch);
  }, [defaultTargetBranch, targetBranch]);

  const toggleBranch = (branch: string) => {
    setSelectedBranches(prev => {
      const next = new Set(prev);
      if (next.has(branch)) next.delete(branch);
      else next.add(branch);
      return next;
    });
  };

  const selectAll = () => {
    setSelectedBranches(new Set(availableBranches.map(b => b.branch)));
  };

  const deselectAll = () => {
    setSelectedBranches(new Set());
  };

  return (
    <div className="intCreateForm">
      <h3 className="intFormTitle">创建集成单</h3>
      <div className="intFormField">
        <label className="intFormLabel">目标分支</label>
        <input
          className="intFormInput"
          list="integration-target-branches"
          value={targetBranch}
          onChange={e => setTargetBranch(e.target.value)}
          placeholder={defaultTargetBranch || "输入目标分支"}
        />
        <datalist id="integration-target-branches">
          {targetBranches.map(branch => <option key={branch} value={branch} />)}
        </datalist>
      </div>
      <div className="intFormField">
        <label className="intFormLabel">
          选择要集成的 fix 分支
          <span className="intFormCount">（已选 {selectedBranches.size}/{availableBranches.length}）</span>
        </label>
        <div className="intFormActions">
          <button className="btnSmall" onClick={selectAll} type="button">全选</button>
          <button className="btnSmall" onClick={deselectAll} type="button">清空</button>
        </div>
        <div className="intBranchList">
          {availableBranches.length === 0 && <p className="intEmpty">没有可用的 fix/* 分支</p>}
          {availableBranches.map(b => (
            <label key={b.branch} className="intBranchItem">
              <input
                type="checkbox"
                checked={selectedBranches.has(b.branch)}
                onChange={() => toggleBranch(b.branch)}
              />
              <span className="intBranchItemMain">
                <code>{b.branch}</code>
                <small>
                  {b.has_worktree ? "worktree" : "本地分支"}
                  {b.source_commit ? ` · ${b.source_commit.slice(0, 7)}` : ""}
                </small>
              </span>
            </label>
          ))}
        </div>
      </div>
      <div className="intFormButtons">
        <button
          className="button primary"
          disabled={busy || selectedBranches.size === 0 || !targetBranch.trim()}
          onClick={() => onSubmit(workspaceId, targetBranch.trim(), [...selectedBranches])}
        >
          创建集成单
        </button>
        <button className="button ghost" onClick={onCancel} disabled={busy}>取消</button>
      </div>
    </div>
  );
}
