"use client";
import { useRef, useEffect, useMemo, useState, useCallback } from "react";
import XMarkdown from "@ant-design/x-markdown";
import {
  CodeOutlined,
  InfoCircleOutlined,
  RobotOutlined,
  UserOutlined,
  ApiOutlined,
  DownOutlined,
  RightOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
} from "@ant-design/icons";
import { CollapsibleCodeBlock } from "./CollapsibleCodeBlock";

interface LogPaneProps {
  content: string;
  placeholder?: string;
  streaming?: boolean;
}

/* ─── 日志块类型 ─── */

type LogBlock =
  | { type: "cmd"; text: string }
  | { type: "info"; text: string }
  | { type: "user"; text: string }
  | { type: "codex"; text: string }
  | { type: "exec"; commands: string[]; status: string; output: string };

/* ─── 日志解析 ─── */

type ParseState = "info" | "user" | "codex" | "exec-cmds" | "exec-output";

function isSystemInfoLine(line: string): boolean {
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(line)) return true;
  if (
    /^(OpenAI Codex|--------$|workdir:|model:|provider:|approval:|sandbox:|reasoning|session id:|Enable it with)/.test(
      line
    )
  )
    return true;
  if (/^Reading prompt from stdin/.test(line)) return true;
  if (/^warning: Ignoring malformed/.test(line)) return true;
  if (/^deprecated: /.test(line)) return true;
  if (/^tokens used$/.test(line)) return true;
  return false;
}

function isSectionMarker(
  line: string
): "user" | "codex" | "exec" | "cmd" | false {
  if (line === "user") return "user";
  if (line === "codex") return "codex";
  if (line === "exec") return "exec";
  if (/^\$ /.test(line)) return "cmd";
  return false;
}

function parseLogBlocks(raw: string): LogBlock[] {
  const lines = raw.split("\n");
  const blocks: LogBlock[] = [];
  let state: ParseState = "info";
  let buffer: string[] = [];
  let execCommands: string[] = [];
  let execStatus = "";

  function flush() {
    const text = buffer.join("\n").trim();
    switch (state) {
      case "info":
        if (text) blocks.push({ type: "info", text });
        break;
      case "user":
        if (text) blocks.push({ type: "user", text });
        break;
      case "codex":
        if (text) blocks.push({ type: "codex", text });
        break;
      case "exec-cmds":
        if (execCommands.length > 0)
          blocks.push({
            type: "exec",
            commands: [...execCommands],
            status: "",
            output: "",
          });
        break;
      case "exec-output":
        blocks.push({
          type: "exec",
          commands: [...execCommands],
          status: execStatus,
          output: buffer.join("\n").trimEnd(),
        });
        break;
    }
    buffer = [];
    execCommands = [];
    execStatus = "";
  }

  for (const line of lines) {
    const marker = isSectionMarker(line);

    if (marker === "cmd") {
      flush();
      blocks.push({ type: "cmd", text: line });
      state = "info";
      continue;
    }
    if (marker === "user") {
      flush();
      state = "user";
      continue;
    }
    if (marker === "codex") {
      flush();
      state = "codex";
      continue;
    }
    if (marker === "exec") {
      if (state === "exec-cmds") {
        /* 并行执行 — 归入同一逻辑块 */
      } else {
        flush();
        state = "exec-cmds";
      }
      continue;
    }

    /* exec-cmds：检测 succeeded/failed 或累积命令行 */
    if (state === "exec-cmds") {
      if (/^ succeeded/.test(line) || /^ failed/.test(line)) {
        execStatus = line.trim();
        state = "exec-output";
      } else {
        execCommands.push(line);
      }
      continue;
    }

    /* exec-output：累积输出直到遇到下一个标记 */
    if (state === "exec-output") {
      buffer.push(line);
      continue;
    }

    /* user/codex：系统信息行会打断当前段落 */
    if ((state === "user" || state === "codex") && isSystemInfoLine(line)) {
      flush();
      state = "info";
      buffer.push(line);
      continue;
    }

    /* 默认：累积当前行 */
    buffer.push(line);
  }
  flush();
  return blocks;
}

/* ─── Markdown 组件覆盖 ─── */

const markdownComponents = {
  code: CollapsibleCodeBlock,
};

/* ─── 工具函数：缩短执行命令用于展示 ─── */

function shortenExecCmd(cmd: string): string {
  const m = cmd.match(/^\/bin\/\w+\s+-lc\s+"(.+?)"\s+in\s+/);
  if (m) return m[1];
  return cmd;
}

/* ─── 日志块渲染器 ─── */

function CmdBlock({ text }: { text: string }) {
  return (
    <div className="vsc-log-cmd">
      <CodeOutlined className="vsc-log-cmd-icon" />
      <span className="vsc-log-cmd-text">{text}</span>
    </div>
  );
}

function InfoBlock({ text }: { text: string }) {
  return (
    <div className="vsc-log-info">
      <InfoCircleOutlined className="vsc-log-info-icon" />
      <pre className="vsc-log-info-text">{text}</pre>
    </div>
  );
}

function UserBlock({ text }: { text: string }) {
  return (
    <div className="vsc-log-user">
      <div className="vsc-log-user-avatar">
        <UserOutlined />
      </div>
      <div className="vsc-log-user-body">
        <XMarkdown components={markdownComponents}>{text}</XMarkdown>
      </div>
    </div>
  );
}

function CodexBlock({
  text,
  streaming,
}: {
  text: string;
  streaming: boolean;
}) {
  return (
    <div className="vsc-log-md">
      <div className="vsc-log-md-avatar">
        <RobotOutlined />
      </div>
      <div className="vsc-log-md-body">
        <XMarkdown
          components={markdownComponents}
          streaming={
            streaming
              ? { hasNextChunk: true, enableAnimation: true, tail: true }
              : undefined
          }
        >
          {text}
        </XMarkdown>
      </div>
    </div>
  );
}

const EXEC_COLLAPSE_THRESHOLD = 15;
const MAX_LINE_LENGTH = 500;
const MAX_OUTPUT_LINES = 200;
const NOISY_LINE_LENGTH = 1200;

function isNoisyLongLine(line: string): boolean {
  if (line.length <= NOISY_LINE_LENGTH) return false;
  const sample = line.slice(0, 2000);
  const whitespaceCount = (sample.match(/\s/g) ?? []).length;
  if (whitespaceCount <= 2) return true;
  const noisyChars = sample.replace(/[A-Za-z0-9+/=,;:_.$'"()[\]{}<>-]/g, "");
  return noisyChars.length / sample.length < 0.08;
}

function sanitizeLogLine(line: string): string {
  if (isNoisyLongLine(line)) {
    return `[… 已省略 ${line.length.toLocaleString()} 字符的压缩/二进制日志 …]`;
  }
  return line.length > MAX_LINE_LENGTH ? `${line.slice(0, MAX_LINE_LENGTH)} …(截断)` : line;
}

/** 过滤/截断二进制垃圾行，保持日志可读 */
function sanitizeLogText(text: string, maxLines = Number.POSITIVE_INFINITY): string {
  const lines = text.split("\n");
  const result: string[] = [];
  let truncated = false;
  for (const line of lines) {
    if (result.length >= maxLines) {
      truncated = true;
      break;
    }
    result.push(sanitizeLogLine(line));
  }
  if (truncated) result.push(`\n… 输出过长，仅显示前 ${maxLines} 行`);
  return result.join("\n");
}

function ExecBlock({
  commands,
  status,
  output,
}: {
  commands: string[];
  status: string;
  output: string;
}) {
  const outputLines = output ? output.split("\n").length : 0;
  const [collapsed, setCollapsed] = useState(
    outputLines > EXEC_COLLAPSE_THRESHOLD
  );

  const isFailed = /failed/.test(status);
  const isSucceeded = /succeeded/.test(status);

  const toggle = useCallback(() => setCollapsed((v) => !v), []);

  return (
    <div
      className={`vsc-log-exec ${isFailed ? "vsc-log-exec--failed" : ""}`}
    >
      <div className="vsc-log-exec-header" onClick={toggle}>
        <button
          className="vsc-log-exec-toggle"
          type="button"
          aria-expanded={!collapsed}
        >
          {collapsed ? (
            <RightOutlined style={{ fontSize: 10 }} />
          ) : (
            <DownOutlined style={{ fontSize: 10 }} />
          )}
        </button>
        <ApiOutlined className="vsc-log-exec-icon" />
        <span className="vsc-log-exec-cmds">
          {commands.map((c) => shortenExecCmd(c)).join(" ; ")}
        </span>
        {status && (
          <span
            className={`vsc-log-exec-status ${isFailed ? "vsc-log-exec-status--failed" : ""}`}
          >
            {isSucceeded ? (
              <CheckCircleOutlined style={{ fontSize: 11 }} />
            ) : (
              <CloseCircleOutlined style={{ fontSize: 11 }} />
            )}
            <span>{status}</span>
          </span>
        )}
      </div>
      {!collapsed && output && (
        <pre className="vsc-log-exec-output">{sanitizeLogText(output, MAX_OUTPUT_LINES)}</pre>
      )}
    </div>
  );
}

/* ─── 主组件 ─── */

export default function LogPane({
  content,
  placeholder,
  streaming = false,
}: LogPaneProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [content]);

  const blocks = useMemo(() => {
    if (!content) return [];
    return parseLogBlocks(sanitizeLogText(content));
  }, [content]);

  if (!content) {
    return (
      <div className="vsc-logpane vsc-logpane-empty">
        <RobotOutlined style={{ fontSize: 24, opacity: 0.3 }} />
        <span>{placeholder || "当前分支暂无执行日志。"}</span>
      </div>
    );
  }

  return (
    <div className="vsc-logpane" ref={scrollRef}>
      {blocks.map((block, i) => {
        const isLast = i === blocks.length - 1;
        switch (block.type) {
          case "cmd":
            return <CmdBlock key={i} text={block.text} />;
          case "info":
            return <InfoBlock key={i} text={block.text} />;
          case "user":
            return <UserBlock key={i} text={block.text} />;
          case "codex":
            return (
              <CodexBlock
                key={i}
                text={block.text}
                streaming={isLast && streaming}
              />
            );
          case "exec":
            return (
              <ExecBlock
                key={i}
                commands={block.commands}
                status={block.status}
                output={block.output}
              />
            );
        }
      })}
    </div>
  );
}
