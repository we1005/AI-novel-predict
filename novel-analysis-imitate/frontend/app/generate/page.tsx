"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function GeneratePage() {
  const [books, setBooks] = useState<any[]>([]);
  const [composeList, setComposeList] = useState<any[]>([]);
  const [voice, setVoice] = useState("");
  const [cslug, setCslug] = useState("");
  const [title, setTitle] = useState("");
  const [summary, setSummary] = useState("");
  const [must, setMust] = useState("");
  const [wordTarget, setWordTarget] = useState("2000");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [exportText, setExportText] = useState("");

  const refreshCompose = () => api.composeList().then(setComposeList).catch(() => {});
  useEffect(() => {
    api.books().then((bs) => { setBooks(bs); if (bs[0]) setVoice(bs[0].slug); })
      .catch((e) => setMsg("无法连接后端 :8100 — " + e.message));
    refreshCompose();
  }, []);

  async function run() {
    if (!cslug || !voice || !summary) { setMsg("请填写:产物名、文风源、本章梗概"); return; }
    setBusy(true); setMsg("① 建虚拟书 + 落大纲…"); setExportText("");
    try {
      await api.uc2({
        cslug, voice_source: voice, overwrite: true,
        chapters: [{
          chapter_index: 1, title: title || "第1章", summary,
          must_include: must.split(/[,，\s]+/).filter(Boolean),
          word_target: Number(wordTarget) || 2000,
        }],
      });
      setMsg("② 后台生成中(数十秒,小米 mimo-v2.5-pro 仿写 + 三审一编辑)…");
      await api.generate(cslug, 1, false);
      // 轮询导出
      for (let i = 0; i < 40; i++) {
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
      <div className="h1">仿写 / 重组生成</div>
      <div className="sub">UC2:用某书的文风写你的故事(声音迁移、内容不串)。UC1/3/4 见后端 API。</div>

      <div className="card">
        <h2>用 A 的文风写我的故事</h2>
        <div className="row" style={{ marginBottom: 10 }}>
          <label className="muted" style={{ width: 70 }}>文风源</label>
          <select value={voice} onChange={(e) => setVoice(e.target.value)}>
            {books.map((b) => <option key={b.slug} value={b.slug}>{b.title || b.slug}</option>)}
          </select>
          <input placeholder="产物书名(英数中文皆可)" value={cslug} onChange={(e) => setCslug(e.target.value)}
            style={inp} />
        </div>
        <div className="row" style={{ marginBottom: 10 }}>
          <label className="muted" style={{ width: 70 }}>本章标题</label>
          <input placeholder="第1章 标题" value={title} onChange={(e) => setTitle(e.target.value)} style={{ ...inp, flex: 1 }} />
          <input placeholder="目标字数" value={wordTarget} onChange={(e) => setWordTarget(e.target.value.replace(/\D/g, ""))} style={{ ...inp, width: 100 }} />
        </div>
        <textarea placeholder="本章梗概(你的故事剧情)" value={summary} onChange={(e) => setSummary(e.target.value)}
          style={{ ...inp, width: "100%", height: 90, marginBottom: 10 }} />
        <div className="row">
          <input placeholder="must_include 关键词(逗号分隔)" value={must} onChange={(e) => setMust(e.target.value)} style={{ ...inp, flex: 1 }} />
          <button className="btn" onClick={run} disabled={busy}>{busy ? "生成中…" : "生成本章"}</button>
        </div>
        {msg && <div className="muted" style={{ marginTop: 10, fontSize: 13 }}>{msg}</div>}
      </div>

      {exportText && (
        <div className="card">
          <h2>生成正文 <span className="tag">{cslug}</span></h2>
          <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.85, fontSize: 14.5 }}>{exportText}</div>
        </div>
      )}

      <div className="card">
        <h2>已生成的产物书 <span className="tag">点击查看</span></h2>
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
  background: "var(--panel-2)", color: "var(--text)", border: "1px solid var(--border)",
  borderRadius: 8, padding: "8px 12px", fontSize: 13,
};
