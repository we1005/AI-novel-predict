import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "墨析 · 跨书深度分析",
  description: "中文中长篇小说技法/文笔/世界观/节奏/关系深度拆解",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
