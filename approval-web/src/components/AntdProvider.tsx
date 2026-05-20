"use client";
import { ConfigProvider, App } from "antd";
import zhCN from "antd/locale/zh_CN";
import type { ReactNode } from "react";

const theme = {
  token: {
    colorPrimary: "#3b82f6",
    colorSuccess: "#10b981",
    colorError: "#ef4444",
    colorWarning: "#f59e0b",
    borderRadius: 8,
    fontFamily:
      '-apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", system-ui, sans-serif',
  },
};

export function AntdProvider({ children }: { children: ReactNode }) {
  return (
    <ConfigProvider locale={zhCN} theme={theme}>
      <App>{children}</App>
    </ConfigProvider>
  );
}
