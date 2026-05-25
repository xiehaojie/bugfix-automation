import { CloudDownload, Eye, Loader2 } from "lucide-react";

import type { OnlineSheetPreview, OnlineSheetProviderOption } from "../types";

type OnlineSheetPanelProps = {
  providers: OnlineSheetProviderOption[];
  provider: string;
  url: string;
  range: string;
  preview: OnlineSheetPreview | null;
  busyAction: string;
  onProviderChange: (provider: string) => void;
  onUrlChange: (url: string) => void;
  onRangeChange: (range: string) => void;
  onPreview: () => void | Promise<void>;
  onImport: () => void | Promise<void>;
};

export function OnlineSheetPanel({
  providers,
  provider,
  url,
  range,
  preview,
  busyAction,
  onProviderChange,
  onUrlChange,
  onRangeChange,
  onPreview,
  onImport,
}: OnlineSheetPanelProps) {
  const previewing = busyAction === "/api/online-sheets/preview";
  const importing = busyAction === "/api/online-sheets/import";
  const disabled = Boolean(busyAction);
  const providerItems = providers.length
    ? providers
    : [
        { key: "feishu", label: "飞书文档" },
        { key: "dingtalk", label: "钉钉文档" },
        { key: "tencent_docs", label: "腾讯文档" },
        { key: "wps", label: "金山/WPS" },
      ];

  return (
    <div className="onlineSheetPanel">
      <div className="configFieldRow">
        <div className="configField">
          <label className="configLabel">在线表格平台</label>
          <select className="configSelect" value={provider} onChange={event => onProviderChange(event.target.value)}>
            {providerItems.map(item => (
              <option key={item.key} value={item.key}>{item.label}</option>
            ))}
          </select>
        </div>
        <div className="configField">
          <label className="configLabel">读取范围</label>
          <input className="configInput" value={range} onChange={event => onRangeChange(event.target.value)} placeholder="A1:Z1000" />
        </div>
      </div>
      <div className="configField">
        <label className="configLabel">在线表格链接</label>
        <input className="configInput" value={url} onChange={event => onUrlChange(event.target.value)} placeholder="粘贴飞书/钉钉/腾讯文档/WPS 表格链接" />
        <span className="configHint">第一版会读取在线表格并转成当前系统使用的 xlsx，后续仍复用 Excel 识别和筛选规则</span>
      </div>
      <div className="configScheduleRow">
        <button className="buttonSmall ghost" disabled={disabled || !url.trim()} onClick={() => void onPreview()}>
          {previewing ? <Loader2 size={13} className="spin" /> : <Eye size={13} />}
          预览
        </button>
        <button className="buttonSmall secondary" disabled={disabled || !url.trim()} onClick={() => void onImport()}>
          {importing ? <Loader2 size={13} className="spin" /> : <CloudDownload size={13} />}
          导入并切换
        </button>
      </div>

      {preview ? (
        <div className="onlineSheetPreview">
          <div className="onlineSheetPreviewMeta">
            <strong>{preview.row_count}</strong> 行 · {preview.headers.length} 列 · {preview.range}
          </div>
          <div className="onlineSheetPreviewHeaders">
            {preview.headers.map(header => <code key={header}>{header}</code>)}
          </div>
          {preview.rows.length ? (
            <pre className="promptContent">{JSON.stringify(preview.rows.slice(0, 3), null, 2)}</pre>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

