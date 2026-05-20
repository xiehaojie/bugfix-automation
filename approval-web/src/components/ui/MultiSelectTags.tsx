import { Check, ChevronDown, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent } from "react";
import { createPortal } from "react-dom";

export interface OptionItem {
  value: string;
  label?: string;
  count?: number;
}

interface MultiSelectTagsProps {
  value: string[];
  options: OptionItem[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  allowCustom?: boolean;
  disabled?: boolean;
  emptyText?: string;
  /** When true, only one item can be selected. */
  single?: boolean;
}

export function MultiSelectTags({
  value,
  options,
  onChange,
  placeholder = "选择…",
  allowCustom = true,
  disabled = false,
  emptyText = "无可选项",
  single = false,
}: MultiSelectTagsProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const wrapRef = useRef<HTMLDivElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const [dropdownStyle, setDropdownStyle] = useState<CSSProperties | null>(null);

  const recalcPosition = () => {
    if (!wrapRef.current) return;
    const rect = wrapRef.current.getBoundingClientRect();
    const spaceBelow = window.innerHeight - rect.bottom;
    const spaceAbove = rect.top;
    const measuredHeight = dropdownRef.current?.offsetHeight ?? 240;
    const preferredHeight = Math.min(240, measuredHeight);
    const showAbove = spaceBelow < preferredHeight + 8 && spaceAbove > spaceBelow;
    const maxHeight = Math.max(120, Math.min(240, (showAbove ? spaceAbove : spaceBelow) - 12));

    setDropdownStyle({
      position: "fixed",
      left: rect.left,
      width: rect.width,
      maxHeight,
      zIndex: 9999,
      ...(showAbove ? { bottom: window.innerHeight - rect.top + 4 } : { top: rect.bottom + 4 }),
    });
  };

  useEffect(() => {
    if (!open) return;
    recalcPosition();
    const rafId = window.requestAnimationFrame(recalcPosition);
    window.addEventListener("scroll", recalcPosition, true);
    window.addEventListener("resize", recalcPosition);
    return () => {
      window.cancelAnimationFrame(rafId);
      window.removeEventListener("scroll", recalcPosition, true);
      window.removeEventListener("resize", recalcPosition);
    };
  }, [open]);

  useEffect(() => {
    if (!disabled && open) return;
    setOpen(false);
  }, [disabled, open]);

  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      const target = e.target as Node;
      const clickedTrigger = wrapRef.current?.contains(target);
      const clickedDropdown = dropdownRef.current?.contains(target);
      if (!clickedTrigger && !clickedDropdown) setOpen(false);
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, [open]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return options;
    return options.filter(o =>
      (o.label ?? o.value).toLowerCase().includes(q) || o.value.toLowerCase().includes(q)
    );
  }, [options, query]);

  const toggle = (v: string) => {
    if (single) {
      onChange([v]);
      setOpen(false);
      return;
    }
    if (value.includes(v)) onChange(value.filter(x => x !== v));
    else onChange([...value, v]);
  };

  const remove = (v: string) => onChange(value.filter(x => x !== v));

  const addCustom = () => {
    const v = query.trim();
    if (!v || value.includes(v)) return;
    if (single) onChange([v]);
    else onChange([...value, v]);
    setQuery("");
  };

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && allowCustom && query.trim()) {
      e.preventDefault();
      addCustom();
    } else if (e.key === "Backspace" && !query && value.length > 0) {
      onChange(value.slice(0, -1));
    }
  };

  const labelFor = (v: string) =>
    options.find(o => o.value === v)?.label ?? v;

  const customValue = query.trim();
  const canAddCustom = allowCustom && customValue && !options.some(o => o.value === customValue);
  const showEmpty = filtered.length === 0 && !canAddCustom;

  return (
    <div className="multiSelect" ref={wrapRef}>
      <div
        className={`multiSelectControl ${open ? "open" : ""} ${disabled ? "disabled" : ""}`}
        onClick={() => {
          if (!disabled) setOpen(true);
        }}
        aria-disabled={disabled}
      >
        <div className="multiSelectTags">
          {value.map(v => (
            <span className="multiSelectTag" key={v}>
              {labelFor(v)}
              <button
                type="button"
                className="multiSelectTagX"
                onClick={(e) => {
                  e.stopPropagation();
                  if (!disabled) remove(v);
                }}
                title="移除"
                disabled={disabled}
              >
                <X size={11} />
              </button>
            </span>
          ))}
          <input
            className="multiSelectInput"
            value={query}
            onChange={e => {
              setQuery(e.target.value);
              if (!disabled) setOpen(true);
            }}
            onKeyDown={onKeyDown}
            placeholder={value.length === 0 ? placeholder : ""}
            onFocus={() => {
              if (!disabled) setOpen(true);
            }}
            disabled={disabled}
          />
        </div>
        <ChevronDown size={14} className="multiSelectChevron" />
      </div>

      {open && dropdownStyle && typeof document !== "undefined"
        ? createPortal(
          <div className="multiSelectDropdown" ref={dropdownRef} style={dropdownStyle}>
            {showEmpty ? (
              <div className="multiSelectEmpty">{emptyText}</div>
            ) : (
            <>
              {filtered.map(opt => {
                const selected = value.includes(opt.value);
                return (
                  <button
                    type="button"
                    key={opt.value}
                    className={`multiSelectOption ${selected ? "selected" : ""}`}
                    onClick={() => toggle(opt.value)}
                  >
                    <span className="multiSelectCheck">
                      {selected ? <Check size={12} /> : null}
                    </span>
                    <span className="multiSelectLabel">{opt.label ?? opt.value}</span>
                    {typeof opt.count === "number" ? (
                      <span className="multiSelectCount">{opt.count}</span>
                    ) : null}
                  </button>
                );
              })}
              {canAddCustom ? (
                <button
                  type="button"
                  className="multiSelectOption add"
                  onClick={addCustom}
                >
                  <span className="multiSelectCheck">＋</span>
                  <span className="multiSelectLabel">添加自定义：「{customValue}」</span>
                </button>
              ) : null}
            </>
            )}
          </div>,
          document.body
        )
        : null}
    </div>
  );
}
