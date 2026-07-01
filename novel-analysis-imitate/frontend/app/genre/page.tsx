"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import Icon from "@/components/Icon";
import Link from "next/link";

type Tpl = {
  slug: string; name: string; source_slugs: string[];
  template?: any; system_prompt?: string; updated_at?: string;
};

const FIELDS: { k: string; t: string }[] = [
  { k: "imagery", t: "核心意象池" },
  { k: "motifs", t: "母题 / 套路" },
  { k: "worldview_lexicon", t: "世界观语汇" },
  { k: "atmosphere", t: "氛围基调" },
  { k: "flavor_recipe", t: "味道要诀" },
  { k: "syntactic_patterns", t: "题材惯用句式 / 翻译腔" },
  { k: "cliche_sentence_templates", t: "套路句式模板(避免)" },
  { k: "anti_patterns", t: "负面清单 · 词汇(避免)" },
];

export default function GenrePage() {
  const [books, setBooks] = useState<any[]>([]);
  const [list, setList] = useState<Tpl[]>([]);
  const [name, setName] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const [sel, setSel] = useState<Tpl | null>(null);
  const [topic, setTopic] = useState("");
  const [genreStrength, setGenreStrength] = useState(70);   // 旋钮①:类型味浓度
  const [novelty, setNovelty] = useState(60);               // 旋钮②:求异度
  const [previewText, setPreviewText] = useState("");
  const [busy, setBusy] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [msg, setMsg] = useState("");
  // 抽样策略(按字数比例 + 全书均匀铺开)
  const [sample, setSample] = useState<any>({ ratio: 0.005, min_chars: 3000, max_chars: 20000, spread: 16 });
  const [showSample, setShowSample] = useState(false);

  const refresh = () => api.genreList().then(setList).catch(() => {});
  useEffect(() => {
    api.books().then(setBooks).catch((e) => setMsg("无法连接后端 :8100 — " + e.message));
    api.genreSampleConfigGet().then((c) => c && setSample((s: any) => ({ ...s, ...c }))).catch(() => {});
    refresh();
  }, []);

  const setS = (k: string, v: number) => setSample((s: any) => ({ ...s, [k]: v }));

  const toggle = (slug: string) =>
    setPicked((p) => (p.includes(slug) ? p.filter((x) => x !== slug) : [...p, slug]));

  async function open(slug: string) {
    setPreviewText(""); setMsg("");
    try { setSel(await api.genreGet(slug)); }
    catch (e: any) { setMsg("拉取失败: " + e.message); }
  }

  async function extract() {
    if (!name.trim() || picked.length < 2) { setMsg("请填模板名,且至少选 2 本同题材的书"); return; }
    setBusy(true); setMsg("正在抽取(蒸馏多书语义层,约 15–40 秒)…"); setSel(null);
    try {
      const r = await api.genreExtract({ name: name.trim(), source_slugs: picked, sample });
      if (r.error) { setMsg("失败:" + r.error); setBusy(false); return; }
      const slug = r.slug;
      // 后台抽取,轮询直到就绪
      for (let i = 0; i < 40; i++) {
        await new Promise((res) => setTimeout(res, 2500));
        const rec = await api.genreGet(slug);
        if (rec && !rec.error && rec.template) { setSel(rec); await refresh(); setMsg("✅ 抽取完成"); break; }
        if (i === 39) setMsg("仍在抽取,稍后在左侧列表点开查看");
      }
    } catch (e: any) { setMsg("失败: " + e.message); }
    finally { setBusy(false); }
  }

  async function doPreview() {
    if (!sel || !topic.trim()) { setMsg("请填一个场景主题"); return; }
    setPreviewing(true); setPreviewText(""); setMsg("");
    try {
      const r = await api.genrePreview(sel.slug, topic.trim(), genreStrength, novelty);
      setPreviewText(r.error ? "错误:" + r.error : r.text);
    } catch (e: any) { setMsg("preview 失败: " + e.message); }
    finally { setPreviewing(false); }
  }

  async function del(slug: string) {
    if (!confirm(`删除模板「${slug}」?`)) return;
    await api.genreDelete(slug).catch(() => {});
    if (sel?.slug === slug) setSel(null);
    refresh();
  }

  const arr = (v: any) => Array.isArray(v) ? v : (v ? [String(v)] : []);

  return (
    <div className="applayout">
      <aside className="rail">
        <Link href="/" className="railbrand"><span className="railseal">墨</span><span>墨析</span></Link>
        <nav className="railnav">
          <Link href="/" className="railitem"><Icon k="analyze" /><span>深度分析</span></Link>
          <Link href="/generate" className="railitem"><Icon k="compose" /><span>仿写 · 重组</span></Link>
          <Link href="/genre" className="railitem active"><Icon k="style" /><span>类型模板</span></Link>
          <Link href="/architecture" className="railitem"><Icon k="arch" /><span>架构</span></Link>
          <Link href="/genome" className="railitem"><Icon k="style" /><span>文风基因组</span></Link>
        </nav>
      </aside>

      <main className="appmain">
        <div style={{ display: "grid", gridTemplateColumns: "340px 1fr", gap: 20, alignItems: "start" }}>
        {/* 左:抽取 + 列表 */}
        <div>
          <div className="card" style={{ marginBottom: 16 }}>
            <h3 style={{ marginTop: 0 }}>抽取通用类型模板</h3>
            <p className="muted" style={{ fontSize: 12, marginTop: -4 }}>
              选 ≥2 本<strong>同题材</strong>的书,从它们的语义层蒸出可复用的"写作配方"(纯语义,不含作者句式)。
            </p>
            <input placeholder="模板名(如:克苏鲁维多利亚)" value={name}
              onChange={(e) => setName(e.target.value)}
              style={{ width: "100%", padding: 8, marginBottom: 10 }} />
            <div style={{ maxHeight: 220, overflow: "auto", border: "1px solid var(--rule,#d6d0bf)", borderRadius: 6, padding: 8 }}>
              {books.map((b) => (
                <label key={b.slug} style={{ display: "flex", gap: 8, alignItems: "center", padding: "3px 0", fontSize: 13, cursor: "pointer" }}>
                  <input type="checkbox" checked={picked.includes(b.slug)} onChange={() => toggle(b.slug)} />
                  <span>{b.slug}</span>
                </label>
              ))}
            </div>

            {/* 抽样策略:按字数比例 + 全书均匀铺开(可调 + 存为默认)*/}
            <div style={{ marginTop: 10, fontSize: 12 }}>
              <div onClick={() => setShowSample((v) => !v)}
                style={{ cursor: "pointer", color: "var(--zhe,#9a6b2f)", fontWeight: 600 }}>
                {showSample ? "▾" : "▸"} 抽样策略(按字数比例)
                <span className="muted" style={{ fontWeight: "normal" }}> · 每本 ≈{(sample.ratio * 100).toFixed(2)}%字数,夹在 {sample.min_chars}–{sample.max_chars} 字</span>
              </div>
              {showSample && (
                <div style={{ marginTop: 8, padding: 10, background: "var(--paper,#f1efe5)", borderRadius: 6, display: "grid", gap: 8 }}>
                  <label>比例(每本取全书的 %) <strong>{(sample.ratio * 100).toFixed(2)}%</strong>
                    <input type="range" min={0.1} max={3} step={0.1} value={sample.ratio * 100}
                      onChange={(e) => setS("ratio", Number(e.target.value) / 100)} style={{ width: "100%" }} />
                  </label>
                  <div style={{ display: "flex", gap: 8 }}>
                    <label style={{ flex: 1 }}>下限字数
                      <input type="number" value={sample.min_chars} min={500} step={500}
                        onChange={(e) => setS("min_chars", Number(e.target.value))} style={{ width: "100%" }} /></label>
                    <label style={{ flex: 1 }}>上限字数
                      <input type="number" value={sample.max_chars} min={sample.min_chars} step={500}
                        onChange={(e) => setS("max_chars", Number(e.target.value))} style={{ width: "100%" }} /></label>
                    <label style={{ width: 70 }}>取样段数
                      <input type="number" value={sample.spread} min={1} max={20}
                        onChange={(e) => setS("spread", Number(e.target.value))} style={{ width: "100%" }} /></label>
                  </div>
                  <div className="muted" style={{ fontSize: 11 }}>
                    按字符位置在全书均匀取样(非按章节,修长短章偏差);上限防长书淹没短书;下限=上限即“等量模式”。
                  </div>
                  <button className="ghost" style={{ fontSize: 12, padding: "4px 10px", justifySelf: "start" }}
                    onClick={() => api.genreSampleConfigPut(sample).then(() => setMsg("✅ 已存为默认抽样策略")).catch(() => setMsg("保存失败"))}>
                    保存为默认
                  </button>
                </div>
              )}
            </div>

            <button onClick={extract} disabled={busy}
              style={{ marginTop: 10, width: "100%", padding: "8px 0" }}>
              {busy ? "抽取中…" : `抽取(已选 ${picked.length} 本)`}
            </button>
          </div>

          <div className="card">
            <h3 style={{ marginTop: 0 }}>已保存模板</h3>
            {list.length === 0 && <p className="muted" style={{ fontSize: 12 }}>还没有模板</p>}
            {list.map((t) => (
              <div key={t.slug} style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
                padding: "6px 8px", borderRadius: 6, cursor: "pointer",
                background: sel?.slug === t.slug ? "var(--ruleSoft,#e6e1d1)" : "transparent" }}
                onClick={() => open(t.slug)}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: 13 }}>{t.name}</div>
                  <div className="muted" style={{ fontSize: 11 }}>{(t.source_slugs || []).length} 本源书</div>
                </div>
                <button onClick={(e) => { e.stopPropagation(); del(t.slug); }}
                  className="ghost" style={{ fontSize: 11, padding: "2px 8px" }}>删</button>
              </div>
            ))}
          </div>
        </div>

        {/* 右:详情 + preview */}
        <div>
          {msg && <p style={{ fontSize: 13, color: msg.startsWith("✅") ? "var(--good,#2e7d32)" : "var(--zhu,#c0392b)" }}>{msg}</p>}
          {!sel && <div className="card muted">从左侧选/抽一个模板查看详情、试写。</div>}
          {sel && (
            <>
              <div className="card" style={{ marginBottom: 16 }}>
                <h2 style={{ marginTop: 0 }}>{sel.name}
                  <span className="muted" style={{ fontSize: 12, fontWeight: "normal", marginLeft: 10 }}>
                    源:{(sel.source_slugs || []).join(" · ")}
                  </span>
                </h2>
                {FIELDS.map((f) => {
                  const v = sel.template?.[f.k];
                  if (!v || (Array.isArray(v) && !v.length)) return null;
                  const isSyntax = f.k === "syntactic_patterns" || f.k === "cliche_sentence_templates";
                  return (
                    <div key={f.k} style={{ marginBottom: 8 }}>
                      <div style={{ fontWeight: 600, fontSize: 13 }}>
                        {f.t}
                        {isSyntax && <span className="muted" style={{ fontSize: 11, fontWeight: "normal" }}> · 分析参考(当前不进试写)</span>}
                      </div>
                      <div style={{ fontSize: 13, color: "var(--bone,#574f40)" }}>
                        {Array.isArray(v) ? arr(v).join(" · ") : String(v)}
                      </div>
                    </div>
                  );
                })}
                <details style={{ marginTop: 10 }}>
                  <summary style={{ cursor: "pointer", fontSize: 13, fontWeight: 600 }}>可调用的 system_prompt</summary>
                  <pre style={{ whiteSpace: "pre-wrap", fontSize: 12, background: "var(--paper,#f1efe5)", padding: 10, borderRadius: 6 }}>
                    {sel.system_prompt}
                  </pre>
                </details>
              </div>

              <div className="card">
                <h3 style={{ marginTop: 0 }}>试写(用该模板现写一段)</h3>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 12 }}>
                  <label style={{ fontSize: 13 }}>
                    类型味浓度 <strong>{genreStrength}</strong>
                    <span className="muted" style={{ fontSize: 11 }}>（轻触 → 浓墨重彩）</span>
                    <input type="range" min={0} max={100} step={5} value={genreStrength}
                      onChange={(e) => setGenreStrength(Number(e.target.value))}
                      style={{ width: "100%" }} />
                  </label>
                  <label style={{ fontSize: 13 }}>
                    求异度 <strong>{novelty}</strong>
                    <span className="muted" style={{ fontSize: 11 }}>（稳妥 → 大胆求异）</span>
                    <input type="range" min={0} max={100} step={5} value={novelty}
                      onChange={(e) => setNovelty(Number(e.target.value))}
                      style={{ width: "100%" }} />
                  </label>
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <input placeholder="场景主题,如:雾夜停尸间,尸体胸腔仍在起伏"
                    value={topic} onChange={(e) => setTopic(e.target.value)}
                    style={{ flex: 1, padding: 8 }} />
                  <button onClick={doPreview} disabled={previewing} style={{ padding: "8px 16px" }}>
                    {previewing ? "写作中…" : "试写"}
                  </button>
                </div>
                {previewText && (
                  <div style={{ marginTop: 12, whiteSpace: "pre-wrap", fontSize: 14, lineHeight: 1.8,
                    background: "var(--paper,#f1efe5)", padding: 14, borderRadius: 8 }}>
                    {previewText}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
        </div>
      </main>
    </div>
  );
}
