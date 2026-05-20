import { Loader2, Plus, Save, Trash2, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { MultiSelectTags } from "../../../components/ui/MultiSelectTags";
import type { FilterRule } from "../types";

const OP_OPTIONS = [
  { value: "equals", label: "等于" },
  { value: "not_equals", label: "不等于" },
  { value: "in", label: "包含任一" },
  { value: "not_in", label: "不含任一" },
  { value: "all_in", label: "全部在内" },
  { value: "contains", label: "文本包含" },
  { value: "not_contains", label: "文本不包含" },
];

const MULTI_OPS = new Set(["in", "not_in", "all_in"]);

interface ColumnOption {
  value: string;
  count: number;
}

interface ExcelColumns {
  headers: string[];
  columns: Record<string, ColumnOption[]>;
}

interface EditorRule {
  id: string;
  field: string;
  op: string;
  values: string[];
}

let editorRuleId = 0;

function nextEditorRuleId(): string {
  editorRuleId += 1;
  return `filter-rule-${editorRuleId}`;
}

function rulesFromConfig(rules: FilterRule[]): EditorRule[] {
  return rules.map(r => ({
    id: nextEditorRuleId(),
    field: r.field,
    op: r.op,
    values: MULTI_OPS.has(r.op)
      ? (r.values?.length ? r.values : r.value ? [r.value] : [])
      : (r.value ? [r.value] : (r.values?.[0] ? [r.values[0]] : [])),
  }));
}

interface FilterRulesEditorProps {
  rules: FilterRule[];
  onSave: (rules: FilterRule[]) => Promise<void>;
  onCancel: () => void;
}

export function FilterRulesEditor({ rules, onSave, onCancel }: FilterRulesEditorProps) {
  const [draft, setDraft] = useState<EditorRule[]>(rulesFromConfig(rules));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [columns, setColumns] = useState<ExcelColumns>({ headers: [], columns: {} });
  const [colsLoading, setColsLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    fetch("/api/excel/columns")
      .then(r => r.json())
      .then(data => {
        if (!alive) return;
        if (data?.ok) {
          setColumns({ headers: data.headers || [], columns: data.columns || {} });
        }
      })
      .catch(() => { /* ignore */ })
      .finally(() => { if (alive) setColsLoading(false); });
    return () => { alive = false; };
  }, []);

  const fieldOptions = useMemo(
    () => columns.headers.map(h => ({ value: h, label: h })),
    [columns.headers]
  );

  const update = (index: number, patch: Partial<EditorRule>) => {
    setDraft(prev => prev.map((r, i) => i === index ? { ...r, ...patch } : r));
  };

  const add = () => {
    setDraft(prev => [...prev, { id: nextEditorRuleId(), field: "", op: "equals", values: [] }]);
  };

  const remove = (index: number) => {
    setDraft(prev => prev.filter((_, i) => i !== index));
  };

  const handleSave = async () => {
    const built: FilterRule[] = draft
      .filter(r => r.field.trim() && r.values.length > 0)
      .map(r => {
        if (MULTI_OPS.has(r.op)) {
          return { field: r.field.trim(), op: r.op, value: "", values: r.values };
        }
        return { field: r.field.trim(), op: r.op, value: r.values[0] ?? "", values: [] };
      });
    setBusy(true);
    setError("");
    try {
      await onSave(built);
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="filterEditor">
      {error ? <div className="filterEditorError">{error}</div> : null}
      {colsLoading ? (
        <div className="filterEditorHint"><Loader2 size={11} className="spin" /> 正在加载 Excel 列…</div>
      ) : columns.headers.length === 0 ? (
        <div className="filterEditorHint">未读取到 Excel 列。请先在「数据源」上传或选择 Excel。</div>
      ) : null}

      <div className="filterEditorRows">
        {draft.map((rule, index) => {
          const valueOptions = (columns.columns[rule.field] || []).map(o => ({
            value: o.value,
            label: o.value,
            count: o.count,
          }));
          const isMulti = MULTI_OPS.has(rule.op);
          return (
            <div className="filterEditorRow" key={rule.id}>
              <div className="filterEditorTopRow">
                <div className="filterEditorField">
                  <MultiSelectTags
                    value={rule.field ? [rule.field] : []}
                    options={fieldOptions}
                    onChange={(next: string[]) => {
                      const nextField = next[next.length - 1] || "";
                      update(index, { field: nextField, values: nextField === rule.field ? rule.values : [] });
                    }}
                    placeholder="选择字段"
                    single
                    allowCustom={false}
                    disabled={colsLoading || columns.headers.length === 0}
                    emptyText="未读取到 Excel 列"
                  />
                </div>
                <div className="filterEditorOp">
                  <select
                    className="filterSelect"
                    value={rule.op}
                    title="筛选操作符"
                    onChange={e => {
                      const nextOp = e.target.value;
                      const nextValues = !MULTI_OPS.has(nextOp) ? rule.values.slice(0, 1) : rule.values;
                      update(index, { op: nextOp, values: nextValues });
                    }}
                  >
                    {OP_OPTIONS.map(opt => (
                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                    ))}
                  </select>
                </div>
                <button className="filterRemoveBtn" onClick={() => remove(index)} title="删除">
                  <X size={13} />
                </button>
              </div>
              <div className="filterEditorValue">
                <MultiSelectTags
                  value={rule.values}
                  options={valueOptions}
                  onChange={(next: string[]) => update(index, { values: isMulti ? next : next.slice(-1) })}
                  placeholder={rule.field ? (isMulti ? "选择多个值" : "选择值") : "请先选择字段"}
                  single={!isMulti}
                  allowCustom={Boolean(rule.field)}
                  disabled={!rule.field}
                  emptyText={rule.field ? "该字段暂无可选值" : "请先选择字段"}
                />
              </div>
            </div>
          );
        })}
      </div>

      <div className="filterEditorActions">
        <button className="buttonSmall ghost" onClick={add}>
          <Plus size={13} />添加规则
        </button>
        <div className="filterEditorRight">
          <button className="buttonSmall ghost" onClick={onCancel} disabled={busy}>
            <Trash2 size={13} />取消
          </button>
          <button className="buttonSmall secondary" onClick={() => void handleSave()} disabled={busy}>
            {busy ? <Loader2 size={13} className="spin" /> : <Save size={13} />}
            保存
          </button>
        </div>
      </div>
    </div>
  );
}
