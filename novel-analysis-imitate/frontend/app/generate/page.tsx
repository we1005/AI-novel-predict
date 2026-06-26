"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

const UCS = [
  { k: "uc2", t: "UC2 · 用A文风写我的故事" },
  { k: "uc1", t: "UC1 · 融合多书世界观+文风" },
  { k: "uc4", t: "UC4 · 江南技法注入(自动蒸馏)" },
  { k: "uc3", t: "UC3 · 跨书剧情移植到新世界观" },
];

export default function GeneratePage() {
  const [books, setBooks] = useState<any[]>([]);
  const [composeList, setComposeList] = useState<any[]>([]);
  const [uc, setUc] = useState("uc2");
  const [voice, setVoice] = useState("");
  const [cslug, setCslug] = useState("");
  const [title, setTitle] = useState("");
  const [summary, setSummary] = useState("");
  const [must, setMust] = useState("");
  const [wordTarget, setWordTarget] = useState("2000");
  const [fuse, setFuse] = useState<string[]>([]);       // UC1 融合源
  const [plot, setPlot] = useState<string[]>([]);       // UC3 剧情源
  const [techSrc, setTechSrc] = useState("");           // UC4 技法源
  const [anchor, setAnchor] = useState("");             // UC3 目标世界观
  const [nCh, setNCh] = useState("2");                  // UC3 章数
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [exportText, setExportText] = useState("");

  const refreshCompose = () => api.composeList().then(setComposeList).catch(() => {});
  useEffect(() => {
    api.books().then((bs) => { setBooks(bs); if (bs[0]) setVoice(bs[0].slug); })
      .catch((e) => setMsg("无法连接后端 :8100 — " + e.message));
    refreshCompose();
  }, []);

  const oneChapter = () => ([{
    chapter_index: 1, title: title || "第1章", summary,
    must_include: must.split(/[,，\s]+/).filter(Boolean),
    word_target: Number(wordTarget) || 2000,
  }]);
  const toggle = (arr: string[], set: any, v: string) =>
    set(arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]);

  async function run() {
    if (!cslug || !voice) { setMsg("请填写产物名与文风源"); return; }
    const needSummary = uc !== "uc3";
    if (needSummary && !summary) { setMsg("请填写本章梗概"); return; }
    if (uc === "uc3" && !anchor) { setMsg("UC3 需填目标世界观"); return; }
    setBusy(true); setMsg("① 建虚拟书 + 落大纲…"); setExportText("");
    try {
      if (uc === "uc2") await api.uc2({ cslug, voice_source: voice, overwrite: true, chapters: oneChapter() });
      else if (uc === "uc1") await api.uc1({ cslug, voice_source: voice, fuse_sources: fuse.length ? fuse : [voice], overwrite: true, chapters: oneChapter() });
      else if (uc === "uc4") await api.uc4({ cslug, voice_source: voice, technique_source: techSrc || voice, overwrite: true, chapters: oneChapter() });
      else if (uc === "uc3") await api.uc3({ cslug, voice_source: voice, plot_sources: plot.length ? plot : [voice], anchor_world: anchor, n_chapters: Number(nCh) || 2, overwrite: true });
      setMsg("② 后台生成第1章中(数十秒,小米 mimo-v2.5-pro)…");
      await api.generate(cslug, 1, false);
      for (let i = 0; i < 45; i++) {
        await new Promise((r) => setTimeout(r, 4000));
        const ex = await api.exportCompose(cslug);
        if (ex.text && ex.text.length > 50) { setExportText(ex.text); setMsg("✓ 生成完成"); break; }
        setMsg(`② 生成中…(${(i + 1) * 4}s)`);
      }
      refreshCompose();
    } catch (e: any) { setMsg("失败: " + e.message); }
    finally { setBusy(false); }
  }

  async function view(cs: string) {
    setMsg("加载产物…");
    try { const ex = await api.exportCompose(cs); setExportText(ex.text || "(空)"); setCslug(cs); setMsg(""); }
    catch (e: any) { setMsg("失败: " + e.message); }
  }

  return (
    <div className="wrap">
      <span className="eyebrow">COMPOSE · 借声成文</span>
      <div className="h1">借一本书的笔法,写另一个故事</div>
      <div className="sub">虚拟书载入源书的声音与笔法,沿用三审一编辑的续写内核。四类重组共用一条生成路径。</div>

      <div className="tabs">
        {UCS.map((x) => <div key={x.k} className={"tab" + (uc === x.k ? " active" : "")} onClick={() => setUc(x.k)}>{x.t}</div>)}
      </div>

      <div className="card">
        <div className="row" style={{ marginBottom: 10 }}>
          <label className="muted" style={{ width: 80 }}>文风源</label>
          <select value={voice} onChange={(e) => setVoice(e.target.value)}>
            {books.map((b) => <option key={b.slug} value={b.slug}>{b.title || b.slug}</option>)}
          </select>
          <input placeholder="产物书名" value={cslug} onChange={(e) => setCslug(e.target.value)} style={inp} />
        </div>

        {uc === "uc1" && (
          <div style={{ marginBottom: 10 }}>
            <label className="muted">融合文风源(多选)</label>
            <div>{books.map((b) => (
              <span key={b.slug} className="pill" style={{ cursor: "pointer", borderColor: fuse.includes(b.slug) ? "var(--zhu)" : undefined }}
                onClick={() => toggle(fuse, setFuse, b.slug)}>{fuse.includes(b.slug) ? "✓ " : ""}{b.title || b.slug}</span>
            ))}</div>
          </div>
        )}
        {uc === "uc4" && (
          <div className="row" style={{ marginBottom: 10 }}>
            <label className="muted" style={{ width: 80 }}>技法源</label>
            <select value={techSrc || voice} onChange={(e) => setTechSrc(e.target.value)}>
              {books.map((b) => <option key={b.slug} value={b.slug}>{b.title || b.slug}</option>)}
            </select>
            <span className="muted" style={{ fontSize: 12 }}>从该书分析层自动蒸馏导演手册(需先跑分析)</span>
          </div>
        )}
        {uc === "uc3" && (
          <>
            <div style={{ marginBottom: 10 }}>
              <label className="muted">剧情母核源(多选,抽取去设定剧情)</label>
              <div>{books.map((b) => (
                <span key={b.slug} className="pill" style={{ cursor: "pointer", borderColor: plot.includes(b.slug) ? "var(--zhu)" : undefined }}
                  onClick={() => toggle(plot, setPlot, b.slug)}>{plot.includes(b.slug) ? "✓ " : ""}{b.title || b.slug}</span>
              ))}</div>
            </div>
            <textarea placeholder="目标世界观设定(剧情母核将重锚定到此世界)" value={anchor} onChange={(e) => setAnchor(e.target.value)}
              style={{ ...inp, width: "100%", height: 70, marginBottom: 10 }} />
            <div className="row" style={{ marginBottom: 10 }}>
              <label className="muted" style={{ width: 80 }}>生成章数</label>
              <input value={nCh} onChange={(e) => setNCh(e.target.value.replace(/\D/g, ""))} style={{ ...inp, width: 80 }} />
              <span className="muted" style={{ fontSize: 12 }}>大纲由模型从母核重锚定自动生成</span>
            </div>
          </>
        )}

        {uc !== "uc3" && (
          <>
            <div className="row" style={{ marginBottom: 10 }}>
              <label className="muted" style={{ width: 80 }}>本章标题</label>
              <input placeholder="第1章 标题" value={title} onChange={(e) => setTitle(e.target.value)} style={{ ...inp, flex: 1 }} />
              <input placeholder="字数" value={wordTarget} onChange={(e) => setWordTarget(e.target.value.replace(/\D/g, ""))} style={{ ...inp, width: 90 }} />
            </div>
            <textarea placeholder="本章梗概(你的故事剧情)" value={summary} onChange={(e) => setSummary(e.target.value)}
              style={{ ...inp, width: "100%", height: 84, marginBottom: 10 }} />
            <input placeholder="must_include 关键词(逗号分隔)" value={must} onChange={(e) => setMust(e.target.value)} style={{ ...inp, width: "100%", marginBottom: 10 }} />
          </>
        )}

        <button className="btn" onClick={run} disabled={busy}>{busy ? "生成中…" : "建虚拟书并生成第1章"}</button>
        {msg && <div className="muted" style={{ marginTop: 10, fontSize: 13 }}>{msg}</div>}
      </div>

      {exportText && (
        <div className="card">
          <h2>生成正文 <span className="tag">{cslug}</span></h2>
          <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.85, fontSize: 14.5 }}>{exportText}</div>
        </div>
      )}

      <div className="card">
        <h2>已生成的产物书 <span className="tag">点击查看正文</span></h2>
        {!composeList.length ? <div className="muted">暂无</div> :
          <table><thead><tr><th>产物</th><th>用例</th><th>文风源</th><th>章</th></tr></thead>
            <tbody>{composeList.map((c) => (
              <tr key={c.cslug} style={{ cursor: "pointer" }} onClick={() => view(c.cslug)}>
                <td><a>{c.cslug}</a></td><td>{c.use_case}</td><td className="muted">{c.voice_source}</td>
                <td>{c.outline_run_id ? "✓" : "—"}</td></tr>
            ))}</tbody></table>}
      </div>
    </div>
  );
}

const inp: React.CSSProperties = {
  background: "var(--ink-2)", color: "var(--bone)", border: "1px solid var(--rule)",
  borderRadius: 2, padding: "9px 12px", fontSize: 13,
};
