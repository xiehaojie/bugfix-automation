import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Bug 修复审批台",
  description: "本地 bug 自动修复审批工作台"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
