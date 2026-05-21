import { Copy, Edit3, Image as ImageIcon, Loader2, RotateCcw, Sparkles, Wand2, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { fetchJson } from "../api";
import type { BugItem } from "../types";

type PromptPreviewProps = {
  bug: BugItem;
  onClose: () => void;
  onRunWithPrompt: (bug: BugItem) => void;
};

type PreviewResponse = {
  ok: boolean;
  prompt: string;
  images?: Array<{ path: string; name: string; url: string }>;
};

export function PromptPreview({ bug, onClose, onRunWithPrompt }: PromptPreviewProps) {
  const [prompt, setPrompt] = useState("");
  const [originalPrompt, setOriginalPrompt] = useState("");
  const [loading, setLoading] = useState(false);
  const [optimizing, setOptimizing] = useState(false);
  const [editing, setEditing] = useState(false);
  const [copied, setCopied] = useState(false);
  const [images, setImages] = useState<Array<{ path: string; name: string; url: string }>>([]);

  const loadPrompt = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchJson<PreviewResponse>("/api/bugs/preview-prompt", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ excel_row: bug.excel_row }),
      });
      setPrompt(data.prompt);
      setOriginalPrompt(data.prompt);
      setImages(data.images ?? []);
    } catch (error) {
      setPrompt(`加载失败: ${error instanceof Error ? error.message : "未知错误"}`);
    } finally {
      setLoading(false);
    }
  }, [bug.excel_row]);

  useEffect(() => {
    void loadPrompt();
  }, [loadPrompt]);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(prompt);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleOptimize = async () => {
    setOptimizing(true);
    try {
      const data = await fetchJson<{ ok: boolean; prompt?: string; error?: string }>("/api/bugs/optimize-prompt", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ excel_row: bug.excel_row, prompt }),
      });
      if (data.ok && data.prompt) {
        setPrompt(data.prompt);
      } else {
        setPrompt(prev => `${prev}\n\n/* 优化失败: ${data.error ?? "未知错误"} */`);
      }
    } catch (error) {
      setPrompt(prev => `${prev}\n\n/* 优化失败: ${error instanceof Error ? error.message : "未知错误"} */`);
    } finally {
      setOptimizing(false);
    }
  };

  const handleReset = () => {
    setPrompt(originalPrompt);
    setEditing(false);
  };

  return (
    <div className="promptOverlay" onClick={onClose}>
      <div className="promptModal" onClick={event => event.stopPropagation()}>
        <header className="promptModalHeader">
          <div className="promptModalTitle">
            <Sparkles size={18} />
            <h3>提示词预览</h3>
            <span className="promptMeta">序号 {bug.issue_id} · 行 {bug.excel_row}</span>
          </div>
          <button className="promptModalClose" onClick={onClose}><X size={18} /></button>
        </header>

        <div className="promptDesc">
          <strong>{bug.description || "未填写问题描述"}</strong>
          <span>{bug.primary_category} / {bug.secondary_category}</span>
        </div>

        {/* Images section */}
        {images.length > 0 ? (
          <div className="promptImages">
            <div className="promptImagesLabel"><ImageIcon size={14} />截图 ({images.length})</div>
            <div className="promptImageGrid">
              {images.map(img => (
                <a key={img.path} href={img.url} target="_blank" rel="noreferrer" title={img.name}>
                  <img src={img.url} alt={img.name} />
                </a>
              ))}
            </div>
          </div>
        ) : null}

        <div className="promptBody">
          {loading ? (
            <div className="promptLoading">
              <Loader2 size={20} className="spin" />
              <span>正在生成提示词…</span>
            </div>
          ) : editing ? (
            <textarea
              className="promptTextarea"
              value={prompt}
              onChange={event => setPrompt(event.target.value)}
              autoFocus
            />
          ) : (
            <pre className="promptContent">{prompt}</pre>
          )}
        </div>

        <footer className="promptModalFooter">
          <div className="promptFooterLeft">
            <button className="button ghost" onClick={() => setEditing(!editing)} disabled={loading || !prompt}>
              <Edit3 size={14} />
              {editing ? "预览" : "编辑"}
            </button>
            <button className="button ghost" onClick={() => void handleOptimize()} disabled={loading || optimizing || !prompt}>
              {optimizing ? <Loader2 size={14} className="spin" /> : <Wand2 size={14} />}
              {optimizing ? "优化中…" : "AI 优化"}
            </button>
            {prompt !== originalPrompt ? (
              <button className="button ghost" onClick={handleReset} disabled={loading}>
                <RotateCcw size={14} />
                还原
              </button>
            ) : null}
          </div>
          <div className="promptFooterRight">
            <button className="button ghost" onClick={() => void handleCopy()} disabled={loading || !prompt}>
              <Copy size={14} />
              {copied ? "已复制" : "复制提示词"}
            </button>
            <button
              className="button primary"
              disabled={loading || !prompt}
              onClick={() => onRunWithPrompt(bug)}
            >
              <Sparkles size={14} />
              确认执行 AI
            </button>
          </div>
        </footer>
      </div>
    </div>
  );
}
