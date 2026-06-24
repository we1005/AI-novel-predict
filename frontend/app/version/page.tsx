"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import PageTitle from "@/components/PageTitle";

export default function VersionPage() {
  const [status, setStatus] = useState<any>(null);
  const [commits, setCommits] = useState<any[]>([]);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState("");
  const [revertCh, setRevertCh] = useState("");
  const [branch, setBranch] = useState("");

  const reload = () => {
    api.repoStatus().then(setStatus).catch(() => {});
    api.repoHistory().then((d) => setCommits(d.commits || [])).catch(() => {});
  };
  useEffect(reload, []);

  const run = async (label: string, fn: () => Promise<any>) => {
    setBusy(label); setMsg("");
    try { const r = await fn(); setMsg("✅ " + JSON.stringify(r).slice(0, 200)); reload(); }
    catch (e: any) { setMsg("❌ " + String(e).slice(0, 200)); }
    finally { setBusy(""); }
  };

  return (
    <>
      <PageTitle title="书稿版本控制"
        subtitle="Git 管「源」(正文/大纲/记忆增量) · SQLite 是可重建缓存 · 可按章撤回 / 分支并行 / 删库重物化" />

      <div className="card">
        <h2>仓库状态</h2>
        {status ? (
          <div style={{ fontSize: 13, lineHeight: 1.9 }}>
            <div>路径：<code style={{ fontSize: 12 }}>{status.repo}</code></div>
            <div>已初始化：{status.initialized ? "✅" : "❌"} · 已成稿章节：<b>{(status.chapters || []).length}</b> · 抽取增量：<b>{status.increments}</b> 章</div>
            <div className="muted" style={{ fontSize: 12 }}>章节：{(status.chapters || []).join(", ") || "—"}</div>
          </div>
        ) : <p className="muted">加载中…</p>}
        <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
          <button disabled={!!busy} onClick={() => run("materialize", api.repoMaterialize)}>
            {busy === "materialize" ? "重建中…" : "🔄 从 git 重建记忆 (materialize)"}
          </button>
          <button className="ghost" disabled={!!busy} onClick={() => run("baseline", api.repoBaseline)}>
            📸 重新快照 baseline
          </button>
        </div>
        {msg && <p style={{ fontSize: 12, marginTop: 8, color: msg.startsWith("✅") ? "var(--good)" : "var(--bad)" }}>{msg}</p>}
      </div>

      <div className="row" style={{ gap: 14, alignItems: "stretch" }}>
        <div className="card" style={{ flex: 1, marginBottom: 0 }}>
          <h2>撤回本章</h2>
          <p className="muted" style={{ fontSize: 12 }}>删该章正文 + 抽取增量 → 重新物化，记忆与正文一起干净回退。</p>
          <div style={{ display: "flex", gap: 8 }}>
            <input value={revertCh} onChange={(e) => setRevertCh(e.target.value)} placeholder="章号，如 200"
              style={{ width: 120, padding: "7px 10px", borderRadius: 6, border: "1px solid var(--border)", background: "var(--panel)", color: "inherit" }} />
            <button disabled={!!busy || !revertCh} onClick={() => run("revert", () => api.repoRevertChapter(Number(revertCh)))}>撤回</button>
          </div>
        </div>
        <div className="card" style={{ flex: 1, marginBottom: 0 }}>
          <h2>新建分支（剧情换走向）</h2>
          <p className="muted" style={{ fontSize: 12 }}>在分支上重写某段之后的章节，多结局并行探索，随时切回。</p>
          <div style={{ display: "flex", gap: 8 }}>
            <input value={branch} onChange={(e) => setBranch(e.target.value)} placeholder="分支名，如 what-if-185"
              style={{ flex: 1, padding: "7px 10px", borderRadius: 6, border: "1px solid var(--border)", background: "var(--panel)", color: "inherit" }} />
            <button disabled={!!busy || !branch} onClick={() => run("branch", () => api.repoBranch(branch))}>建分支</button>
          </div>
        </div>
      </div>

      <div className="card" style={{ marginTop: 14 }}>
        <h2>提交历史</h2>
        {commits.length === 0 && <p className="muted">暂无提交</p>}
        <div style={{ display: "grid", gap: 4 }}>
          {commits.map((c) => (
            <div key={c.hash} style={{ display: "flex", gap: 10, fontSize: 12, padding: "5px 0", borderBottom: "1px solid var(--border)" }}>
              <code style={{ color: "var(--accent)" }}>{c.hash}</code>
              <span className="muted">{c.date}</span>
              <span>{c.subject}</span>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
