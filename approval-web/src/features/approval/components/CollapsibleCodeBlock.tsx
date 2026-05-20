"use client";
import { useState, useCallback, useRef } from "react";
import {
  CopyOutlined,
  CheckOutlined,
  DownOutlined,
  RightOutlined,
} from "@ant-design/icons";

interface CollapsibleCodeBlockProps {
  lang?: string;
  block?: boolean;
  children?: React.ReactNode;
  className?: string;
  [key: string]: unknown;
}

/** VSCode 风格的可折叠代码块，支持复制按钮和语言标签 */
export function CollapsibleCodeBlock({
  lang,
  block,
  children,
  ...rest
}: CollapsibleCodeBlockProps) {
  // 行内代码 — 直接渲染 <code>
  if (!block) {
    return <code className="vsc-inline-code" {...rest}>{children}</code>;
  }

  const [collapsed, setCollapsed] = useState(false);
  const [copied, setCopied] = useState(false);
  const codeRef = useRef<HTMLPreElement>(null);

  const langLabel = lang?.split(/\s/)[0] || "";

  const handleCopy = useCallback(() => {
    const text = codeRef.current?.textContent ?? "";
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, []);

  const toggleCollapse = useCallback(() => {
    setCollapsed((v) => !v);
  }, []);

  return (
    <div className="vsc-codeblock">
      {/* Header bar */}
      <div className="vsc-codeblock-header">
        <button
          className="vsc-codeblock-collapse-btn"
          onClick={toggleCollapse}
          aria-expanded={!collapsed}
          aria-label={collapsed ? "展开代码块" : "折叠代码块"}
          type="button"
        >
          {collapsed ? (
            <RightOutlined style={{ fontSize: 10 }} />
          ) : (
            <DownOutlined style={{ fontSize: 10 }} />
          )}
        </button>
        {langLabel && <span className="vsc-codeblock-lang">{langLabel}</span>}
        <div className="vsc-codeblock-actions">
          <button
            className="vsc-codeblock-copy-btn"
            onClick={handleCopy}
            title="复制代码"
            type="button"
          >
            {copied ? (
              <CheckOutlined style={{ fontSize: 13, color: "#10b981" }} />
            ) : (
              <CopyOutlined style={{ fontSize: 13 }} />
            )}
          </button>
        </div>
      </div>
      {/* Code body */}
      {!collapsed && (
        <pre ref={codeRef} className="vsc-codeblock-body">
          <code>{children}</code>
        </pre>
      )}
    </div>
  );
}
