import { Loader2, Save, Sparkles, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import type { ExcelAdapterSuggestion } from "../types";

type ExcelAdapterPanelProps = {
  adapter: ExcelAdapterSuggestion | null;
  busyAction: string;
  onAnalyze: () => void | Promise<void>;
  onSave: (adapter: ExcelAdapterSuggestion) => void | Promise<void>;
  onClear: () => void;
};

function asArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map(item => String(item)) : [];
}

export function ExcelAdapterPanel({ adapter, busyAction, onAnalyze, onSave, onClear }: ExcelAdapterPanelProps) {
  const [draftText, setDraftText] = useState("");
  const [error, setError] = useState("");

  const analyzing = busyAction === "/api/excel/adapter/analyze";
  const saving = busyAction === "/api/excel/adapter/save";
  const disabled = Boolean(busyAction);

  useEffect(() => {
    if (!adapter) {
      setDraftText("");
      setError("");
      return;
    }
    setDraftText(JSON.stringify(adapter, null, 2));
    setError("");
  }, [adapter]);

  const summary = useMemo(() => {
    if (!adapter) return null;
    return {
      fields: asArray(adapter.prompt?.fields),
      branchSummaryFields: asArray(adapter.branch_summary_fields),
      filters: Array.isArray(adapter.filters) ? adapter.filters : []
    };
  }, [adapter]);

  const handleSave = async () => {
    setError("");
    try {
      const parsed = JSON.parse(draftText) as ExcelAdapterSuggestion;
      if (!parsed || typeof parsed !== "object" || !parsed.canonical_fields || !parsed.prompt) {
        throw new Error("JSON 必须包含 canonical_fields 和 prompt");
      }
      await onSave(parsed);
    } catch (parseError) {
      setError(parseError instanceof Error ? parseError.message : "JSON 解析失败");
    }
  };

  return (
    <div className="configField">
      <label className="configLabel">AI 识别 Excel</label>
      <div className="configScheduleRow">
        <button className="buttonSmall secondary" onClick={() => void onAnalyze()} disabled={disabled}>
          {analyzing ? <Loader2 size={13} className="spin" /> : <Sparkles size={13} />}
          {analyzing ? "识别中…" : "AI 识别 Excel"}
        </button>
        {adapter ? (
          <button className="buttonSmall ghost" onClick={onClear} disabled={saving} title="关闭适配建议">
            <X size={13} />
            关闭
          </button>
        ) : null}
      </div>
      <span className="configHint">读取当前 Excel 表头并生成列映射、提示词字段、摘要字段和筛选规则建议</span>

      {adapter?.warnings?.length ? (
        <div className="filterEditorError">
          {adapter.warnings.map(warning => (
            <div key={warning}>{warning}</div>
          ))}
        </div>
      ) : null}

      {summary ? (
        <div className="configField">
          <label className="configLabel">识别结果</label>
          <pre className="promptContent">{[
            `传给 AI 的列：${summary.fields.join(", ") || "未识别"}`,
            `分支摘要字段：${summary.branchSummaryFields.join(", ") || "未识别"}`,
            `筛选规则：${summary.filters.length ? `${summary.filters.length} 条` : "无"}`
          ].join("\n")}</pre>
        </div>
      ) : null}

      {adapter ? (
        <>
          <div className="configField">
            <label className="configLabel">适配建议 JSON</label>
            <textarea
              className="configTextarea"
              value={draftText}
              onChange={event => setDraftText(event.target.value)}
              rows={14}
              spellCheck={false}
            />
            <span className="configHint">可直接修改 canonical_fields、prompt.template、prompt.fields、branch_summary_fields 和 filters 后保存</span>
          </div>
          {error ? <div className="filterEditorError">{error}</div> : null}
          <div className="configSaveRow">
            <button className="button secondary" onClick={() => void handleSave()} disabled={disabled || !draftText.trim()}>
              {saving ? <Loader2 size={14} className="spin" /> : <Save size={14} />}
              保存适配
            </button>
          </div>
        </>
      ) : null}
    </div>
  );
}
