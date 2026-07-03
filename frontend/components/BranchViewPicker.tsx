"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

/**
 * 「视角」下拉:在原著与其各大纲分支之间切换某个视图的数据源(图谱/宝物功法/疑点)。
 * value="" 表示原文(当前 active 书);否则为某分支 slug。分支记忆彼此隔离。
 * 当前 active 书没有分支时,组件不渲染(返回 null),不占位。
 */
export default function BranchViewPicker({
  value, onChange, style,
}: {
  value: string;
  onChange: (v: string) => void;
  style?: React.CSSProperties;
}) {
  const [activeSlug, setActiveSlug] = useState("");
  const [branches, setBranches] = useState<any[]>([]);

  useEffect(() => {
    api.booksList().then((d: any) => {
      setActiveSlug(d?.active || "");
      setBranches((d?.books || []).filter((b: any) => b.is_branch && b.parent_slug === d?.active));
    }).catch(() => {});
  }, []);

  if (branches.length === 0) return null;

  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6, ...style }}>
      <span className="muted" style={{ fontSize: 12 }}>视角</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{ maxWidth: 220 }}
        title="切换到某条大纲分支的视图(各分支记忆隔离,互不影响)"
      >
        <option value="">原文（{activeSlug}）</option>
        {branches.map((b) => (
          <option key={b.slug} value={b.slug}>分支 · {b.branch_name || b.slug}</option>
        ))}
      </select>
    </span>
  );
}
