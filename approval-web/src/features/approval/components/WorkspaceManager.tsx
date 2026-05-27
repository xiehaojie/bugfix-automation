import { ChevronRight, Folder, FolderOpen, Loader2, Plus, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { fetchJson } from "../api";
import type { Workspace } from "../types";

type WorkspaceManagerProps = {
  workspaces: Workspace[];
  activeWorkspace: string;
  onClose: () => void;
  onRefresh: () => void;
};

const SCOPE_OPTIONS = [
  { value: "frontend", label: "前端" },
  { value: "backend", label: "后端" },
  { value: "fullstack", label: "全栈" },
  { value: "custom", label: "自定义" },
];

const SCOPE_DEFAULTS: Record<string, { contextPaths: string; scopePaths: string }> = {
  frontend: { contextPaths: "src/app\nsrc/components", scopePaths: "" },
  backend: { contextPaths: "internal\ncmd", scopePaths: "" },
  fullstack: { contextPaths: "src", scopePaths: "" },
  custom: { contextPaths: "", scopePaths: "" },
};

type BrowseResult = { ok: boolean; current: string; parent: string; dirs: Array<{ name: string; path: string }> };

export function WorkspaceManager({ workspaces, activeWorkspace, onClose, onRefresh }: WorkspaceManagerProps) {
  const [adding, setAdding] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  // New workspace form
  const [name, setName] = useState("");
  const [repoPaths, setRepoPaths] = useState<string[]>([]);
  const [targetAppPath, setTargetAppPath] = useState("");
  const [scope, setScope] = useState("frontend");
  const [scopePaths, setScopePaths] = useState("");
  const [contextPaths, setContextPaths] = useState(SCOPE_DEFAULTS.frontend.contextPaths);

  // Folder picker
  const [showPicker, setShowPicker] = useState(false);
  const [browseDir, setBrowseDir] = useState("~");
  const [browseDirs, setBrowseDirs] = useState<Array<{ name: string; path: string }>>([]);
  const [browseParent, setBrowseParent] = useState("");
  const [browseCurrent, setBrowseCurrent] = useState("");
  const [browseLoading, setBrowseLoading] = useState(false);

  const fetchDirs = useCallback(async (path: string) => {
    setBrowseLoading(true);
    try {
      const data = await fetchJson<BrowseResult>(`/api/browse-dirs?path=${encodeURIComponent(path)}`);
      if (data.ok) {
        setBrowseDirs(data.dirs);
        setBrowseParent(data.parent);
        setBrowseCurrent(data.current);
      }
    } catch { /* ignore */ }
    finally { setBrowseLoading(false); }
  }, []);

  useEffect(() => {
    if (showPicker) void fetchDirs(browseDir);
  }, [showPicker, browseDir, fetchDirs]);

  const handleScopeChange = (newScope: string) => {
    setScope(newScope);
    const defaults = SCOPE_DEFAULTS[newScope] ?? SCOPE_DEFAULTS.custom;
    setContextPaths(defaults.contextPaths);
    setScopePaths(defaults.scopePaths);
  };

  const handlePickerSelect = (path: string) => {
    setRepoPaths(prev => prev.includes(path) ? prev : [...prev, path]);
    setShowPicker(false);
    // Auto-fill name from folder name
    if (!name) {
      const folderName = path.split("/").pop() ?? "";
      setName(folderName);
    }
  };

  const handleAdd = async () => {
    if (!name.trim()) { setError("请填写工作区名称"); return; }
    if (repoPaths.length === 0) { setError("请选择至少一个仓库路径"); return; }
    setBusy("add");
    setError("");
    try {
      const data = await fetchJson<{ ok?: boolean }>("/api/workspace/add", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          repo_paths: repoPaths,
          target_app_path: targetAppPath.trim() || ".",
          scope,
          scope_paths: scopePaths.trim().split("\n").filter(Boolean).join(","),
        }),
      });
      if (data.ok === false) throw new Error("添加失败");
      setAdding(false);
      resetForm();
      onRefresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "添加失败");
    } finally {
      setBusy("");
    }
  };

  const handleRemove = async (workspaceId: string) => {
    setBusy(`remove-${workspaceId}`);
    setError("");
    try {
      const data = await fetchJson<{ ok?: boolean }>("/api/workspace/remove", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workspace_id: workspaceId }),
      });
      if (data.ok === false) throw new Error("删除失败");
      onRefresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除失败");
    } finally {
      setBusy("");
    }
  };

  const handleSelect = async (workspaceId: string) => {
    setBusy(`select-${workspaceId}`);
    setError("");
    try {
      await fetchJson("/api/workspace/select", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workspace_id: workspaceId }),
      });
      onRefresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "切换工作区失败");
    } finally {
      setBusy("");
    }
  };

  const resetForm = () => {
    setName("");
    setRepoPaths([]);
    setTargetAppPath("");
    setScope("frontend");
    setScopePaths("");
    setContextPaths(SCOPE_DEFAULTS.frontend.contextPaths);
  };

  return (
    <div className="promptOverlay" onClick={onClose}>
      <div className="wsManagerModal" onClick={event => event.stopPropagation()}>
        <header className="promptModalHeader">
          <div className="promptModalTitle">
            <FolderOpen size={18} />
            <h3>工作区管理</h3>
            <span className="promptMeta">{workspaces.length} 个工作区</span>
          </div>
          <button className="promptModalClose" onClick={onClose} title="关闭"><X size={18} /></button>
        </header>

        {error ? <div className="wsError">{error}</div> : null}

        <div className="wsBody">
          {/* Existing workspaces list */}
          <div className="wsList">
            {workspaces.map(ws => (
              <div key={ws.id} className={`wsItem ${ws.id === activeWorkspace ? "active" : ""}`}>
                <div className="wsItemMain" onClick={() => void handleSelect(ws.id)}>
                  <div className="wsItemName">
                    <strong>{ws.name}</strong>
                    <span className={`wsScopeBadge ${ws.scope}`}>{SCOPE_OPTIONS.find(o => o.value === ws.scope)?.label ?? ws.scope}</span>
                    {ws.id === activeWorkspace ? <span className="wsActiveBadge">当前</span> : null}
                  </div>
                  <code className="wsItemPath">{(ws.repo_paths?.length > 1 ? ws.repo_paths.map(p => p.split("/").pop()).join(", ") : ws.target_repo)}/{ws.target_app_path}</code>
                  {ws.scope_paths.length > 0 ? <span className="wsItemScopePaths">{ws.scope_paths.length} 个修复目录</span> : null}
                </div>
                <button
                  className="wsItemRemove"
                  disabled={Boolean(busy)}
                  onClick={() => void handleRemove(ws.id)}
                  title="删除工作区"
                >
                  {busy === `remove-${ws.id}` ? <Loader2 size={14} className="spin" /> : <Trash2 size={14} />}
                </button>
              </div>
            ))}
          </div>

          {/* Add workspace form */}
          {adding ? (
            <div className="wsAddForm">
              <h4>添加新工作区</h4>
              <div className="wsFormGrid">
                <label className="wsFormField">
                  <span>名称 *</span>
                  <input value={name} onChange={e => setName(e.target.value)} placeholder="例: PC Web、API Server" />
                </label>
                <label className="wsFormField">
                  <span>仓库路径 * <small>可多选</small></span>
                  <div className="wsInputWithPicker">
                    <div className="wsRepoList">
                      {repoPaths.map((rp, i) => (
                        <span key={rp} className="wsRepoTag">
                          {rp.split("/").pop()}
                          <button type="button" onClick={() => setRepoPaths(prev => prev.filter((_, idx) => idx !== i))} className="wsRepoTagRemove">&times;</button>
                        </span>
                      ))}
                    </div>
                    <button type="button" className="wsPickerBtn" onClick={() => { setShowPicker(true); setBrowseDir(repoPaths[repoPaths.length - 1] || "~"); }}>
                      <FolderOpen size={14} /> 选择
                    </button>
                  </div>
                </label>
                <label className="wsFormField">
                  <span>修复范围</span>
                  <select value={scope} onChange={e => handleScopeChange(e.target.value)}>
                    {SCOPE_OPTIONS.map(opt => <option key={opt.value} value={opt.value}>{opt.label}</option>)}
                  </select>
                </label>
                <label className="wsFormField">
                  <span>应用子路径</span>
                  <input value={targetAppPath} onChange={e => setTargetAppPath(e.target.value)} placeholder="apps/pc-web 或留空表示整个仓库" />
                </label>
                <label className="wsFormField full">
                  <span>修复范围目录 <small>每行一个，AI 只修改这些路径</small></span>
                  <textarea value={scopePaths} onChange={e => setScopePaths(e.target.value)} rows={3} placeholder={"apps/pc-web/src\npackages/shared\nlibs/ui"} />
                </label>
              </div>
              <div className="wsFormActions">
                <button className="button ghost" onClick={() => { setAdding(false); resetForm(); }}>取消</button>
                <button className="button secondary" onClick={() => void handleAdd()} disabled={Boolean(busy)}>
                  {busy === "add" ? <Loader2 size={14} className="spin" /> : <Plus size={14} />}
                  添加工作区
                </button>
              </div>
            </div>
          ) : (
            <button className="wsAddButton" onClick={() => setAdding(true)}>
              <Plus size={16} />
              添加新工作区
            </button>
          )}
        </div>

        {/* Folder picker overlay */}
        {showPicker ? (
          <div className="wsFolderPicker">
            <div className="wsFolderPickerHeader">
              <Folder size={16} />
              <span>选择仓库目录</span>
              <button className="promptModalClose" onClick={() => setShowPicker(false)} title="关闭"><X size={16} /></button>
            </div>
            <div className="wsFolderPickerPath">
              <code>{browseCurrent}</code>
            </div>
            <div className="wsFolderPickerList">
              {browseCurrent !== browseParent ? (
                <button className="wsFolderPickerItem" onClick={() => setBrowseDir(browseParent)}>
                  <Folder size={14} />
                  <span>..</span>
                </button>
              ) : null}
              {browseLoading ? (
                <div className="wsFolderPickerLoading"><Loader2 size={16} className="spin" /></div>
              ) : browseDirs.map(d => (
                <button key={d.path} className="wsFolderPickerItem" onClick={() => setBrowseDir(d.path)}>
                  <Folder size={14} />
                  <span>{d.name}</span>
                  <ChevronRight size={12} className="wsFolderPickerChevron" />
                </button>
              ))}
            </div>
            <div className="wsFolderPickerActions">
              <button className="button ghost" onClick={() => setShowPicker(false)}>取消</button>
              <button className="button secondary" onClick={() => handlePickerSelect(browseCurrent)}>
                选择此目录
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
