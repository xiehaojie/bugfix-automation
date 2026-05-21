"use client";

import { useState, useCallback } from "react";
import { Sender } from "@ant-design/x";
import {
  PaperClipOutlined,
  PictureOutlined,
  SwapOutlined,
} from "@ant-design/icons";
import { Button, Space, Tag, Tooltip, Dropdown } from "antd";
import type { MenuProps } from "antd";
import Image from "next/image";
import LogPane from "./LogPane";
import type { FixItem, LogPayload } from "../types";

/** AI 工具列表 */
const AI_TOOLS = [
  { key: "codex", label: "OpenAI Codex", icon: "/icons/openai.svg" },
  { key: "claude", label: "Claude Code", icon: "/icons/anthropic.svg" },
] as const;

type AiToolKey = (typeof AI_TOOLS)[number]["key"];

interface AiChatPanelProps {
  item: FixItem | null;
  logPayload: LogPayload;
  disabled: boolean;
  loading: boolean;
  onRework: (params: {
    branch: string;
    note: string;
    file_paths: string[];
    image_paths: string[];
    cli_tool?: string;
  }) => Promise<void>;
}

/* ── 主组件 ── */

export function AiChatPanel({
  item,
  logPayload,
  disabled,
  loading,
  onRework,
}: AiChatPanelProps) {
  const [filePaths, setFilePaths] = useState<string[]>([]);
  const [imagePaths, setImagePaths] = useState<string[]>([]);
  const [senderValue, setSenderValue] = useState("");
  const [selectedTool, setSelectedTool] = useState<AiToolKey>("codex");

  /** 下拉菜单：图标 + 名称 */
  const toolMenuItems: MenuProps["items"] = AI_TOOLS.map((t) => ({
    key: t.key,
    label: (
      <span className="aiToolMenuLabel">
        <Image src={t.icon} alt={t.label} width={14} height={14} className="aiToolMenuIcon" />
        {t.label}
      </span>
    ),
  }));

  const currentTool =
    AI_TOOLS.find((t) => t.key === selectedTool) ?? AI_TOOLS[0];

  const handleSubmit = useCallback(
    async (message: string) => {
      if (!message.trim() || !item) return;
      setSenderValue("");
      await onRework({
        branch: item.branch,
        note: message,
        file_paths: filePaths,
        image_paths: imagePaths,
        cli_tool: selectedTool,
      });
      setFilePaths([]);
      setImagePaths([]);
    },
    [item, filePaths, imagePaths, selectedTool, onRework],
  );

  const handleAddFilePath = () => {
    const path = prompt("输入需要关注的文件路径：");
    if (path?.trim()) setFilePaths((prev) => [...prev, path.trim()]);
  };

  const handleAddImagePath = () => {
    const path = prompt("输入截图路径：");
    if (path?.trim()) setImagePaths((prev) => [...prev, path.trim()]);
  };

  const isActive = item?.active ?? false;
  const canSend = Boolean(item) && !disabled && !isActive;

  return (
    <div className="aiChatPanel">
      <div className="aiChatBody">
        {/* AI execution log */}
        <LogPane
          content={logPayload.content}
          streaming={isActive}
          placeholder={item ? "暂无 AI 执行日志" : "选择一个修复项查看对话"}
        />
      </div>

      {/* Attachment tags */}
      {(filePaths.length > 0 || imagePaths.length > 0) && (
        <div className="aiChatAttachments">
          {filePaths.map((f, i) => (
            <Tag
              key={`f-${i}`}
              closable
              onClose={() =>
                setFilePaths((prev) => prev.filter((_, j) => j !== i))
              }
              color="blue"
              style={{ fontSize: 11 }}
            >
              📄 {f.split("/").pop()}
            </Tag>
          ))}
          {imagePaths.map((f, i) => (
            <Tag
              key={`i-${i}`}
              closable
              onClose={() =>
                setImagePaths((prev) => prev.filter((_, j) => j !== i))
              }
              color="purple"
              style={{ fontSize: 11 }}
            >
              🖼️ {f.split("/").pop()}
            </Tag>
          ))}
        </div>
      )}

      {/* Sender */}
      <div className="aiChatSender">
        <Sender
          value={senderValue}
          onChange={setSenderValue}
          onSubmit={handleSubmit}
          loading={loading || isActive}
          disabled={!canSend}
          placeholder={
            item ? "输入补充说明，继续迭代修复…" : "请先选择修复项"
          }
          onCancel={() => {}}
          prefix={
            <Space size={4}>
              <Dropdown
                menu={{
                  items: toolMenuItems,
                  selectedKeys: [selectedTool],
                  onClick: ({ key }) => setSelectedTool(key as AiToolKey),
                }}
                trigger={["click"]}
              >
                <Tooltip title={`当前: ${currentTool.label}，点击切换`}>
                  <Button type="text" size="small" style={{ display: "flex", alignItems: "center", gap: 2 }}>
                    <Image src={currentTool.icon} alt={currentTool.label} width={16} height={16} style={{ opacity: 0.85 }} />
                    <SwapOutlined style={{ fontSize: 10 }} />
                  </Button>
                </Tooltip>
              </Dropdown>
              <Tooltip title="添加文件路径">
                <Button
                  type="text"
                  size="small"
                  icon={<PaperClipOutlined />}
                  onClick={handleAddFilePath}
                />
              </Tooltip>
              <Tooltip title="添加截图路径">
                <Button
                  type="text"
                  size="small"
                  icon={<PictureOutlined />}
                  onClick={handleAddImagePath}
                />
              </Tooltip>
            </Space>
          }
        />
      </div>
    </div>
  );
}
