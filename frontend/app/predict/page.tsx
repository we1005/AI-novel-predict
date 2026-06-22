"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import PageTitle from "@/components/PageTitle";

export default function PredictPage() {
  const [after, setAfter] = useState(0);
  const [lastChapter, setLastChapter] = useState<number | null>(null);
  const [n, setN] = useState(5);
  const [busy, setBusy] = useState(false);
  const [run, setRun] = useState<any | null>(null);
  const [streamText, setStreamText] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [history, setHistory] = useState<any[]>([]);
  const [err, setErr] = useState("");

  useEffect(() => { api.predictList().then(setHistory).catch(() => {}); }, [run]);

  // Default "续写起点" to the book's actual last chapter (book-agnostic).
  useEffect(() => {
    api.chapterCount().then((c: any) => {
      const last = c?.last || c?.total || 0;
      setLastChapter(last);
      setAfter((cur) => (cur === 0 ? last : cur));
    }).catch(() => {});
  }, []);

  const triggerPredict = async () => {
    setBusy(true); setErr(""); setRun(null); setStreamText("");
    try { setRun(await api.predictRun(after, n)); }
    catch (e: any) { setErr(String(e)); }
    finally { setBusy(false); }
  };

  const writeChosen = async (idx: number) => {
    if (!run) return;
    setStreaming(true); setStreamText("");
    try {
      await api.predictWrite(run.id, idx, (chunk) => setStreamText((t) => t + chunk));
    } catch (e: any) { setErr(String(e)); }
    finally { setStreaming(false); }
  };

  // Load a past prediction from the 历史预测 table into the detail view.
  const loadRun = async (id: number) => {
    setErr(""); setStreamText("");
    try {
      const d = await api.predictGet(id);
      setRun(d);
      if (typeof window !== "undefined") window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (e: any) { setErr("加载历史预测失败：" + String(e)); }
  };

  const scoreOf = (idx: number) =>
    run?.scores?.scores?.find((s: any) => s.index === idx);
  const winnerIdx = run?.scores?.winner_index;

  return (
    <>
      <PageTitle title="剧情预测·章" subtitle="下 1-3 章走向：A 发散 → B 4 维校验 → C 流式精写" />
      <div className="card">
        <h2>1. 触发预测（阶段 A 发散 + 阶段 B 校验）</h2>
        <div className="row" style={{ alignItems: "center" }}>
          <label>从第 <input type="number" value={after} onChange={(e) => setAfter(+e.target.value)} style={{ width: 100 }} /> 章之后续写
            {lastChapter != null && <span className="muted" style={{ fontSize: 11, marginLeft: 6 }}>（本书共 {lastChapter} 章）</span>}
          </label>
          <label>候选数 <input type="number" value={n} onChange={(e) => setN(+e.target.value)} style={{ width: 70 }} /></label>
          <button onClick={triggerPredict} disabled={busy}>{busy ? "运行中…" : "运行"}</button>
        </div>
        {run && <p className="muted" style={{ marginTop: 8 }}>本次花费 ${run.cost_usd?.toFixed(4)} · winner: 候选 #{winnerIdx} — {run.scores?.winner_reason}</p>}
      </div>

      {run && (
        <div className="card">
          <h2>2. 候选与评分 {run.after_chapter != null && <span className="muted" style={{ fontSize: 13, fontWeight: 400 }}>（从第 {run.after_chapter} 章 · run #{run.id}）</span>}</h2>
          {(run.candidates ?? []).length === 0 && (
            <p className="muted">这次预测没有候选（多半是早期失败的运行——旧版强制工具调用在大上下文下产出为空，现已改用 JSON-in-text 修复）。请重新点「运行」生成新预测。</p>
          )}
          <div style={{ display: "grid", gap: 12 }}>
            {(run.candidates ?? []).map((c: any, i: number) => {
              const sc = scoreOf(i);
              const isWinner = i === winnerIdx;
              return (
                <div key={i} className="card" style={{
                  marginBottom: 0,
                  borderColor: isWinner ? "var(--accent-2)" : "var(--border)",
                  background: isWinner ? "rgba(187,154,247,.06)" : undefined,
                }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                    <h3>#{i} {c.title} {isWinner && <span className="tag" style={{ background: "var(--accent-2)", color: "#0e1015" }}>WINNER</span>}</h3>
                    <button onClick={() => writeChosen(i)} disabled={streaming}>选这条 → 精写</button>
                  </div>
                  <p>{c.synopsis}</p>
                  <p className="muted">用到的伏笔 id: {(c.uses_foreshadow_ids ?? []).join(", ") || "(无)"}</p>
                  {c.ending_hook && <p className="muted">钩子: {c.ending_hook}</p>}
                  {sc && (
                    <div className="row" style={{ marginTop: 8 }}>
                      <ScoreBar k="自洽" v={sc.coherence} />
                      <ScoreBar k="伏笔" v={sc.foreshadow_use} />
                      <ScoreBar k="人物" v={sc.character_consistency} />
                      <ScoreBar k="新鲜" v={sc.novelty} />
                    </div>
                  )}
                  {sc?.risks?.length > 0 && (
                    <p className="muted" style={{ marginTop: 6 }}>风险: {sc.risks.join("； ")}</p>
                  )}
                  {sc?.verdict && <p className="muted" style={{ marginTop: 6 }}>裁定: {sc.verdict}</p>}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {(streaming || streamText) && (
        <div className="card">
          <h2>3. 精写（流式）</h2>
          <pre style={{ whiteSpace: "pre-wrap", fontFamily: 'ui-serif, "PingFang SC", serif', fontSize: 14, lineHeight: 1.7 }}>{streamText}{streaming && <span className="muted"> ▌</span>}</pre>
        </div>
      )}

      <div className="card">
        <h2>历史预测</h2>
        <p className="muted" style={{ marginTop: -6, fontSize: 12 }}>点击任意一行查看该次预测的候选与评分。</p>
        <table>
          <thead><tr><th>id</th><th>从第几章</th><th>winner</th><th>$</th><th>已精写</th><th>时间</th></tr></thead>
          <tbody>
            {history.map((r) => (
              <tr key={r.id} onClick={() => loadRun(r.id)}
                  style={{ cursor: "pointer", background: run?.id === r.id ? "rgba(187,154,247,.10)" : undefined }}
                  title="点击查看这次预测的候选与评分">
                <td>{r.id}</td>
                <td>{r.after_chapter}</td>
                <td>{r.scores?.winner_index ?? "-"}</td>
                <td>${r.cost_usd?.toFixed(4)}</td>
                <td>{r.has_text ? "✓" : ""}</td>
                <td className="muted">{r.created_at?.replace("T", " ").slice(0, 19)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {err && <div className="card" style={{ borderColor: "var(--bad)" }}>错误：{err}</div>}
    </>
  );
}

function ScoreBar({ k, v }: { k: string; v: number }) {
  const color = v >= 75 ? "var(--good)" : v >= 50 ? "var(--warn)" : "var(--bad)";
  return (
    <div className="metric" style={{ minWidth: 120 }}>
      <div className="k">{k}</div>
      <div className="v" style={{ color }}>{v}</div>
    </div>
  );
}
