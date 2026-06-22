"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useTheme } from "@/components/ThemeProvider";

const FLOW: { key: string; emoji: string; title: string; desc: string; color: string }[] = [
  { key: "/ingest", emoji: "📥", title: "语料", desc: "切分章节，建索引", color: "var(--c-character)" },
  { key: "/graph", emoji: "🧬", title: "图谱", desc: "人物关系 / 伏笔甘特 / 主角演变", color: "var(--c-world)" },
  { key: "/mysteries", emoji: "🔍", title: "疑点", desc: "宏观大问题：主角身份 / 王朝兴衰 / 世界本源", color: "var(--c-mystery)" },
  { key: "/predict", emoji: "💡", title: "预测·章", desc: "下 1-3 章走向候选 + 评分", color: "var(--accent)" },
  { key: "/arc", emoji: "🌌", title: "预测·全弧", desc: "整本故事弧 + 因果图 + 偏好", color: "var(--accent-2)" },
  { key: "/outline", emoji: "📝", title: "大纲", desc: "逐章施工图：意图 / 节奏 / 必含必避", color: "var(--c-foreshadow)" },
  { key: "/draft", emoji: "✒️", title: "成稿", desc: "Writer + 三审 + Editor + ReAct", color: "var(--c-subplot)" },
  { key: "/monitor", emoji: "📊", title: "监控", desc: "Token / 成本 / 各 agent 占比", color: "var(--muted)" },
];

export default function Home() {
  const { theme } = useTheme();
  const [stats, setStats] = useState<any>({});

  useEffect(() => {
    Promise.all([
      api.chapterCount().catch(() => ({ total: 0 })),
      api.batches().catch(() => []),
      api.mysteries().catch(() => []),
      api.outlineList().catch(() => []),
      api.draftList().catch(() => []),
      api.monitorSummary(720).catch(() => ({})),
    ]).then(([c, b, m, o, d, mon]) => {
      setStats({
        chapters: (c as any).total || 0,
        batches_done: (b as any[]).filter((x) => x.status === "done").length,
        mysteries: (m as any[]).length,
        outline_runs: (o as any[]).length,
        drafts: (d as any[]).length,
        cost_usd: (mon as any).cost_usd || 0,
      });
    });
  }, []);

  if (theme === "classic") {
    // Original simple list, kept for the classic theme.
    return (
      <>
        <h1>中文小说续写工具</h1>
        <p className="muted">
          把散落在百万字小说里的伏笔、人物状态、世界规则结构化抽出来，作为续写时的硬约束。
        </p>
        <div className="card" style={{ marginTop: 18 }}>
          <h2>开始</h2>
          <ol>
            {FLOW.map((f) => (
              <li key={f.key}><Link href={f.key}>{f.title} — {f.desc}</Link></li>
            ))}
          </ol>
        </div>
      </>
    );
  }

  // Modern hero homepage
  return (
    <>
      <div style={{
        textAlign: "center", padding: "32px 0 28px",
        borderBottom: "1px solid var(--border)", marginBottom: 28,
      }}>
        <div className="brand-title" style={{
          fontSize: 64, lineHeight: 1, color: "var(--accent-2)", marginBottom: 10,
        }}>
          墨笔
        </div>
        <p style={{
          fontFamily: "var(--serif)", fontSize: 16, color: "var(--muted)", margin: 0, letterSpacing: 2,
        }}>
          中文长篇小说续写 · 多 Agent 协作工具
        </p>
        <p style={{
          fontFamily: "var(--serif)", fontSize: 14, color: "var(--muted)",
          maxWidth: 640, margin: "12px auto 0",
        }}>
          抽取百万字伏笔与人物状态作为创作硬约束 ·
          多 LLM Agent 互检互纠 ·
          逐章大纲到成稿全流程
        </p>
      </div>

      {/* stats strip */}
      <div className="row" style={{ justifyContent: "center", marginBottom: 24 }}>
        <Stat k="语料章节" v={stats.chapters ?? "—"} />
        <Stat k="抽取批次" v={stats.batches_done ?? "—"} />
        <Stat k="宏观疑点" v={stats.mysteries ?? "—"} color="var(--c-mystery)" />
        <Stat k="大纲" v={stats.outline_runs ?? "—"} color="var(--c-foreshadow)" />
        <Stat k="成稿" v={stats.drafts ?? "—"} color="var(--c-subplot)" />
        <Stat k="累计成本" v={stats.cost_usd != null ? `$${(stats.cost_usd as number).toFixed(2)}` : "—"} />
      </div>

      <h2 style={{ fontFamily: "var(--serif)", marginBottom: 14, color: "var(--text)", fontSize: 18 }}>
        创作流程
      </h2>
      <div style={{
        display: "grid", gap: 12,
        gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))",
      }}>
        {FLOW.map((f, i) => (
          <Link key={f.key} href={f.key} style={{ textDecoration: "none" }}>
            <div className="card" style={{
              marginBottom: 0, height: "100%",
              cursor: "pointer", borderTop: `3px solid ${f.color}`,
              transition: "transform 120ms, border-color 120ms",
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                <span style={{ fontSize: 24 }}>{f.emoji}</span>
                <span className="muted" style={{ fontSize: 11 }}>步骤 {i + 1}</span>
              </div>
              <div className="prose-cn" style={{
                fontSize: 18, fontWeight: 600, marginTop: 8, color: "var(--text)",
              }}>
                {f.title}
              </div>
              <p className="muted" style={{ fontSize: 12, lineHeight: 1.55, marginTop: 6, marginBottom: 0 }}>
                {f.desc}
              </p>
            </div>
          </Link>
        ))}
      </div>

      <div style={{ marginTop: 32, padding: "18px 24px", background: "var(--panel-2)", borderRadius: 8,
                    fontFamily: "var(--serif)", fontSize: 14, color: "var(--muted)", textAlign: "center" }}>
        多模型可选（火山引擎 Coding-Plan / 阿里通义）· 写作 minimax-m3 · 全链路 prompt 缓存友好 · SQLite + ChromaDB · React Flow 可视化
      </div>
    </>
  );
}

function Stat({ k, v, color }: { k: string; v: any; color?: string }) {
  return (
    <div className="metric" style={{ minWidth: 110, padding: "12px 18px", textAlign: "center" }}>
      <div className="k" style={color ? { color } : undefined}>{k}</div>
      <div className="v" style={{ fontFamily: "var(--serif)", fontSize: 24 }}>{v}</div>
    </div>
  );
}
