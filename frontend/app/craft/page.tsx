"use client";

import { useEffect, useState, type ReactNode } from "react";
import { api } from "@/lib/api";
import PageTitle from "@/components/PageTitle";

const CAT_LABEL: Record<string, string> = {
  combat: "打斗（单挑/群战/战争）",
  dialogue_subtext: "潜台词对话",
  hook: "章节钩子（开篇/章末）",
};
const CARD_FIELD_LABEL: Record<string, string> = {
  summary: "总体特征", sentence_rhythm: "句式 / 节奏", rhetoric_density: "修辞密度",
  pov_person: "视角 / 人称", info_pacing: "信息释放", signature_vocab: "高频词 / 意象",
  structure_template: "结构模板", do: "该做", dont: "避免",
};

function renderVal(v: any): ReactNode {
  if (v == null || v === "") return null;
  if (typeof v === "string" || typeof v === "number") return String(v).replace(/\*\*/g, "");
  if (Array.isArray(v)) return <ul style={{ margin: 0, paddingLeft: 18 }}>{v.map((x, i) => <li key={i}>{renderVal(x)}</li>)}</ul>;
  if (typeof v === "object") return <div style={{ display: "grid", gap: 3 }}>{Object.entries(v).map(([k, val]) => <div key={k}><span className="muted">{k}：</span>{renderVal(val)}</div>)}</div>;
  return String(v);
}

export default function CraftPage() {
  const [summary, setSummary] = useState<Record<string, any> | null>(null);
  const [cards, setCards] = useState<any[]>([]);
  const [active, setActive] = useState<string>("combat");
  const [snips, setSnips] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const reload = async () => {
    try {
      const [s, c] = await Promise.all([api.craftSummary(), api.craftCards()]);
      setSummary(s); setCards(c);
    } catch (e: any) { setMsg(String(e)); }
  };
  useEffect(() => { reload(); }, []);
  useEffect(() => {
    api.craftSnippets(active, 500).then(setSnips).catch(() => setSnips([]));
  }, [active, summary]);

  const extract = async () => {
    setBusy(true); setMsg("");
    try {
      await api.craftExtract(5, null);
      setMsg("✅ 已后台启动全书抽取（约几分钟）。可稍后刷新本页查看片段数增长与风格卡。");
      const t = setInterval(reload, 8000);
      setTimeout(() => clearInterval(t), 1000 * 60 * 12);
    } catch (e: any) { setMsg(String(e)); }
    finally { setBusy(false); }
  };

  const card = cards.find((c) => c.category === active)?.card;
  const cats = summary ? Object.keys(summary) : ["combat", "dialogue_subtext", "hook"];

  return (
    <>
      <PageTitle title="笔法拆解" subtitle="按类提取原著笔法片段（每类留全部）+ 逐类风格拆解；高分片段会作为写作 few-shot 注入。MVP：打斗 / 潜台词对话 / 章节钩子" />

      <div className="card">
        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <button onClick={extract} disabled={busy}>{busy ? "启动中…" : "⚡ 抽取全书笔法片段"}</button>
          <button onClick={() => api.craftRebuildCards().then(() => { setMsg("已重建风格卡"); reload(); }).catch((e) => setMsg(String(e)))}
            className="ghost" style={{ padding: "4px 10px", fontSize: 12 }}>仅重建风格卡</button>
          <span className="muted" style={{ fontSize: 12 }}>逐批扫全书（便宜模型分类）→ 逐类拆解（强模型）。每类留全部条目。</span>
        </div>
        {msg && <p style={{ fontSize: 12, marginTop: 8, color: msg.startsWith("✅") ? "var(--good)" : "var(--muted)" }}>{msg}</p>}
        <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
          {cats.map((c) => {
            const info = summary?.[c];
            return (
              <button key={c} onClick={() => setActive(c)}
                className={active === c ? "" : "ghost"} style={{ padding: "5px 12px", fontSize: 13 }}>
                {CAT_LABEL[c] || c}{info ? ` · ${info.count}` : ""}
              </button>
            );
          })}
        </div>
      </div>

      {/* 风格卡 */}
      <div className="card">
        <h3 style={{ marginTop: 0 }}>{CAT_LABEL[active] || active} · 风格卡</h3>
        {card ? (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 12 }}>
            {Object.keys(CARD_FIELD_LABEL).filter((k) => card[k] != null && card[k] !== "").map((k) => (
              <div key={k} style={{ minWidth: 0 }}>
                <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 2 }}>{CARD_FIELD_LABEL[k]}</div>
                <div style={{ fontSize: 13, lineHeight: 1.6, overflowWrap: "anywhere" }}>{renderVal(card[k])}</div>
              </div>
            ))}
          </div>
        ) : <p className="muted" style={{ fontSize: 13 }}>暂无风格卡——先点「抽取全书笔法片段」。</p>}
      </div>

      {/* 片段列表 */}
      <div className="card">
        <h3 style={{ marginTop: 0 }}>片段库（{snips.length}，按典型性排序）</h3>
        {snips.length === 0 && <p className="muted" style={{ fontSize: 13 }}>暂无片段。</p>}
        <div style={{ display: "grid", gap: 10 }}>
          {snips.map((s) => (
            <div key={s.id} style={{ background: "var(--panel-2)", borderRadius: 8, padding: "10px 14px", borderLeft: "3px solid var(--accent)" }}>
              <div style={{ display: "flex", gap: 8, alignItems: "baseline", flexWrap: "wrap", marginBottom: 4 }}>
                <span style={{ fontSize: 12, color: "var(--accent-2)", fontWeight: 600 }}>第{s.chapter_number}章</span>
                {s.subtype && <span className="tag" style={{ fontSize: 10 }}>{s.subtype}</span>}
                <span className="muted" style={{ fontSize: 11 }}>典型性 {s.representativeness}</span>
                {(s.tags || []).map((t: string, i: number) => <span key={i} className="muted" style={{ fontSize: 11 }}>#{t}</span>)}
              </div>
              <div style={{ fontSize: 13, lineHeight: 1.7, whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{s.excerpt}</div>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
