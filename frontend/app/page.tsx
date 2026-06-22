"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useTheme } from "@/components/ThemeProvider";

type Step = { key: string; emoji: string; title: string; desc: string; spine?: boolean };
type Stage = { group: string; note: string; color: string; steps: Step[] };

// 引导式工作流：准备 → 规划 → 写作 → 变体。spine=推荐主线。
const STAGES: Stage[] = [
  {
    group: "① 准备语料（一次性）", color: "var(--c-character)",
    note: "把原著嚼成结构化记忆，作为续写的硬约束",
    steps: [
      { key: "/ingest", emoji: "📥", title: "语料导入 · 抽取", spine: true, desc: "切分章节 → 6-agent 抽取实体/伏笔/状态/世界规则/疑点" },
      { key: "/graph", emoji: "🧬", title: "图谱整理", spine: true, desc: "实体去重 · 关系 · 重要度 · 伏笔卡片/甘特" },
      { key: "/style", emoji: "✍️", title: "文笔风格", spine: true, desc: "逆向作者文风画像（开启「仿写」/「双语」开关）" },
    ],
  },
  {
    group: "② 规划剧情", color: "var(--accent-2)",
    note: "先定全局骨架与关键问题，再展开成整本书大纲",
    steps: [
      { key: "/predict", emoji: "💡", title: "剧情预测 · 章", desc: "下 1-3 章走向候选 + 评分（局部探索/试方向）" },
      { key: "/arc", emoji: "🌌", title: "整本故事弧 + 推演", spine: true, desc: "core_truths / 阶段 / 结局 / 体量 → 一键「🌌推演整本书」展开成连续全书大纲 + 完整性裁决" },
    ],
  },
  {
    group: "③ 写作成书（核心）", color: "var(--c-subplot)",
    note: "逐章成稿 → 回灌记忆 → 阶段复审 → 人审放行，滚动写完整本",
    steps: [
      { key: "/arc", emoji: "📖", title: "写整本书（阶段 gate）", spine: true, desc: "在「整本故事弧」页：逐章成稿 → 回灌记忆(下一章读得到) → 每阶段跨章复审(伏笔燃尽/连贯/体量) → 暂停人审 → 续写" },
      { key: "/draft", emoji: "✒️", title: "逐章成稿", desc: "Writer + 三审 + 确定性门控；也可按大纲手动单章打磨/导出" },
      { key: "/outline", emoji: "📝", title: "大纲查看/编辑", desc: "逐章施工图：意图/必含/必避/节奏/钩子，成稿前可手改" },
    ],
  },
  {
    group: "④ 变体 / 进阶（可选）", color: "var(--c-foreshadow)",
    note: "",
    steps: [
      { key: "/style", emoji: "🌐", title: "双语 / 重写文笔", desc: "中英对照再创作（非翻译）· 推翻文笔保主干 re-voice" },
      { key: "/sim", emoji: "🎭", title: "角色仿真", desc: "多角色独立决策多轮互动 → ReportAgent 综合涌现章节" },
      { key: "/mysteries", emoji: "🔍", title: "疑点", desc: "宏观大问题：主角身份/王朝兴衰/世界本源" },
      { key: "/monitor", emoji: "📊", title: "监控", desc: "Token / 成本 / 各 agent 占比" },
    ],
  },
];

const ALL_STEPS = STAGES.flatMap((s) => s.steps);

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
    return (
      <>
        <h1>墨笔 · 中文长篇小说续写</h1>
        <p className="muted">把百万字小说里的伏笔/人物状态/世界规则结构化抽出，作为续写硬约束；规划整本弧，再滚动写完。</p>
        {STAGES.map((st) => (
          <div className="card" key={st.group} style={{ marginTop: 14 }}>
            <h2>{st.group}</h2>
            {st.note && <p className="muted" style={{ marginTop: -6 }}>{st.note}</p>}
            <ol>
              {st.steps.map((f) => (
                <li key={f.title}><Link href={f.key}>{f.title}</Link> — {f.desc}</li>
              ))}
            </ol>
          </div>
        ))}
      </>
    );
  }

  return (
    <>
      <div style={{ textAlign: "center", padding: "32px 0 24px", borderBottom: "1px solid var(--border)", marginBottom: 24 }}>
        <div className="brand-title" style={{ fontSize: 64, lineHeight: 1, color: "var(--accent-2)", marginBottom: 10 }}>墨笔</div>
        <p style={{ fontFamily: "var(--serif)", fontSize: 16, color: "var(--muted)", margin: 0, letterSpacing: 2 }}>
          中文长篇小说续写 · 多 Agent 协作工具
        </p>
        <p style={{ fontFamily: "var(--serif)", fontSize: 14, color: "var(--muted)", maxWidth: 680, margin: "12px auto 0" }}>
          抽取百万字伏笔与人物状态作为创作硬约束 · 规划整本故事弧 · 逐章成稿后回灌记忆滚动写完整本
        </p>
      </div>

      {/* stats strip */}
      <div className="row" style={{ justifyContent: "center", marginBottom: 20 }}>
        <Stat k="语料章节" v={stats.chapters ?? "—"} />
        <Stat k="抽取批次" v={stats.batches_done ?? "—"} />
        <Stat k="宏观疑点" v={stats.mysteries ?? "—"} color="var(--c-mystery)" />
        <Stat k="大纲" v={stats.outline_runs ?? "—"} color="var(--c-foreshadow)" />
        <Stat k="成稿" v={stats.drafts ?? "—"} color="var(--c-subplot)" />
        <Stat k="累计成本" v={stats.cost_usd != null ? `$${(stats.cost_usd as number).toFixed(2)}` : "—"} />
      </div>

      {/* recommended spine */}
      <div style={{ textAlign: "center", marginBottom: 22, fontFamily: "var(--serif)", fontSize: 13.5, color: "var(--muted)" }}>
        推荐主线：
        {ALL_STEPS.filter((s) => s.spine).map((s, i, arr) => (
          <span key={s.title}>
            <span style={{ color: "var(--accent-2)" }}>{s.emoji} {s.title}</span>
            {i < arr.length - 1 && <span style={{ margin: "0 6px", opacity: 0.5 }}>→</span>}
          </span>
        ))}
      </div>

      {/* staged workflow */}
      {STAGES.map((st) => (
        <div key={st.group} style={{ marginBottom: 22 }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 10, paddingLeft: 2, borderLeft: `4px solid ${st.color}`, paddingTop: 2, paddingBottom: 2 }}>
            <h2 style={{ fontFamily: "var(--serif)", margin: 0, fontSize: 17, color: "var(--text)", paddingLeft: 8 }}>{st.group}</h2>
            {st.note && <span className="muted" style={{ fontSize: 12.5 }}>{st.note}</span>}
          </div>
          <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fill, minmax(250px, 1fr))" }}>
            {st.steps.map((f) => (
              <Link key={f.title} href={f.key} style={{ textDecoration: "none" }}>
                <div className="card" style={{
                  marginBottom: 0, height: "100%", cursor: "pointer",
                  borderTop: `3px solid ${st.color}`,
                  outline: f.spine ? "1px solid var(--accent-2)" : "none",
                }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                    <span style={{ fontSize: 24 }}>{f.emoji}</span>
                    {f.spine && <span className="tag" style={{ background: "var(--accent-2)", color: "#0e1015", fontSize: 10 }}>主线</span>}
                  </div>
                  <div className="prose-cn" style={{ fontSize: 17, fontWeight: 600, marginTop: 8, color: "var(--text)" }}>{f.title}</div>
                  <p className="muted" style={{ fontSize: 12, lineHeight: 1.55, marginTop: 6, marginBottom: 0 }}>{f.desc}</p>
                </div>
              </Link>
            ))}
          </div>
        </div>
      ))}

      <div style={{ marginTop: 24, padding: "16px 24px", background: "var(--panel-2)", borderRadius: 8,
                    fontFamily: "var(--serif)", fontSize: 13.5, color: "var(--muted)", textAlign: "center" }}>
        多服务商（火山引擎 Coding-Plan / 阿里通义）· 结构化全部 JSON-in-text · 写作 minimax-m3 ·
        写→回灌记忆反馈环 · 阶段级人审 gate · <Link href="/architecture" style={{ color: "var(--accent)" }}>查看完整架构文档 →</Link>
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
