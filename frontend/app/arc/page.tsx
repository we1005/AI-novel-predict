"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import CausalFlowGraph from "@/components/CausalFlowGraph";
import { useTheme } from "@/components/ThemeProvider";
import { chartPalette } from "@/lib/colors";
import PageTitle from "@/components/PageTitle";

const PHASE_COLORS = ["#7aa2f7", "#bb9af7", "#e0af68", "#f7768e", "#9ece6a", "#7dcfff", "#ff9e64"];

const KIND_COLORS: Record<string, string> = {
  origin: "#bb9af7",
  truth: "#7aa2f7",
  agent: "#f7768e",
  event: "#e0af68",
  consequence: "#9ece6a",
};
const KIND_LABEL: Record<string, string> = {
  origin: "本源",
  truth: "真相",
  agent: "动机",
  event: "事件",
  consequence: "后果",
};

const HINT_PRESETS: { label: string; text: string }[] = [
  { label: "克苏鲁", text: "克苏鲁式的不可名状恐怖：人类在宇宙尺度的真相面前微不足道，理智是奢侈品" },
  { label: "悬疑", text: "悬疑感重，每个真相都引出新的疑问，读者比主角先一步起疑" },
  { label: "中世纪", text: "中世纪低魔奇幻基调，去掉爽点境界堆砌，魔法是稀缺、危险、需要代价的" },
  { label: "宏大", text: "宏大史诗感：多势力对峙、文明兴衰、个人命运嵌入历史洪流" },
  { label: "反网文", text: "脱离网文桎梏：拒绝中二、龙傲天、装逼打脸、境界爽点。重视人物内心、道德困境与代价" },
  { label: "悲剧", text: "悲剧基调：主角不必赢；让重要选择都有不可挽回的代价" },
  { label: "解谜", text: "侦探/解谜结构：每一阶段都围绕一个核心谜题展开，伏笔的揭示就是剧情骨架" },
  { label: "温情", text: "温情向：缩小冲突，放大人际关系、师徒/亲情/爱情的细节" },
];

export default function ArcPage() {
  return (
    <Suspense fallback={<div className="card">加载中…</div>}>
      <ArcPageInner />
    </Suspense>
  );
}

function ArcPageInner() {
  const router = useRouter();
  const search = useSearchParams();
  const initId = search?.get("id");
  const initCandidate = search?.get("candidate");

  const [after, setAfter] = useState(0);
  const [lastChapter, setLastChapter] = useState<number | null>(null);
  const [n, setN] = useState(2);
  const [target, setTarget] = useState(100);
  const [hints, setHints] = useState("");
  const [perCandidate, setPerCandidate] = useState(true);  // true=逐个生成(长章稳) / false=一起生成(短章快)
  const [recommend, setRecommend] = useState<{ recommended: number; low: number; high: number; end_at: number; rationale: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [busySince, setBusySince] = useState<number | null>(null);
  const [tick, setTick] = useState(0);
  const [err, setErr] = useState("");
  const [run, setRun] = useState<any | null>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [openCard, setOpenCard] = useState<number | null>(null);

  // outline_run lookup: key = `${source_kind}|${source_run_id}|${chosen_index}|${phase_index}`
  const [outlineMap, setOutlineMap] = useState<Map<string, number>>(new Map());

  const refreshOutlineMap = async () => {
    try {
      const list = await api.outlineList();
      const m = new Map<string, number>();
      for (const o of list) {
        const k = `${o.source_kind}|${o.source_run_id}|${o.source_chosen_index ?? 0}|${o.phase_index ?? 0}`;
        m.set(k, o.id);
      }
      setOutlineMap(m);
    } catch {}
  };

  useEffect(() => {
    if (!busy) return;
    const t = setInterval(() => setTick((x) => x + 1), 1000);
    return () => clearInterval(t);
  }, [busy]);

  useEffect(() => {
    api.arcList().then(setHistory).catch(() => {});
    refreshOutlineMap();
  }, [run]);

  // Default "起始章节" to the book's actual last chapter (book-agnostic).
  useEffect(() => {
    api.chapterCount().then((c: any) => {
      const last = c?.last || c?.total || 0;
      setLastChapter(last);
      setAfter((cur) => (cur === 0 ? last : cur));
    }).catch(() => {});
  }, []);

  // 推荐续写章数:随起始章节变化(防抖 400ms),依据未收束坑/体量/节奏
  useEffect(() => {
    if (!after) { setRecommend(null); return; }
    const t = setTimeout(() => {
      api.arcRecommendChapters(after).then(setRecommend).catch(() => setRecommend(null));
    }, 400);
    return () => clearTimeout(t);
  }, [after]);

  // Deep-link: load arc by ?id= once on mount
  useEffect(() => {
    if (initId) {
      const id = Number(initId);
      if (Number.isFinite(id)) {
        api.arcGet(id).then((r) => {
          setRun({ id, ...r });
          const candIdx = initCandidate != null ? Number(initCandidate) : (r?.chosen_index ?? 0);
          setOpenCard(Number.isFinite(candIdx) ? candIdx : (r?.chosen_index ?? 0));
        }).catch(() => {});
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Sync URL when run/openCard changes (replace, not push)
  useEffect(() => {
    if (!run?.id) return;
    const params = new URLSearchParams();
    params.set("id", String(run.id));
    if (openCard != null) params.set("candidate", String(openCard));
    router.replace(`/arc?${params.toString()}`, { scroll: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run?.id, openCard]);

  const togglePreset = (text: string) => {
    setHints((cur) => {
      const lines = cur.split("\n").map((l) => l.trim()).filter(Boolean);
      if (lines.includes(text)) return lines.filter((l) => l !== text).join("\n");
      return [...lines, text].join("\n");
    });
  };

  const trigger = async () => {
    setBusy(true);
    setBusySince(Date.now());
    setTick(0);
    setErr("");
    setRun(null);
    setOpenCard(null);
    try {
      const r = await api.arcRun(after, n, target, hints, perCandidate);
      setRun(r);
      setOpenCard(r?.scores?.winner_index ?? 0);
    } catch (e: any) {
      setErr(String(e));
    } finally {
      setBusy(false);
      setBusySince(null);
    }
  };

  const elapsed = busy && busySince ? Math.floor((Date.now() - busySince) / 1000) : 0;

  const loadHistory = async (id: number) => {
    setBusy(true);
    try {
      const r = await api.arcGet(id);
      setRun({ id, ...r });
      setOpenCard(r?.chosen_index ?? 0);
    } finally {
      setBusy(false);
    }
  };

  const loadFromHistory = (h: any) => {
    setAfter(h.after_chapter);
    setTarget(h.target_chapters || 100);
    setHints(h.user_hints || "");
  };

  const winnerIdx = run?.scores?.winner_index;
  const scoreOf = (i: number) =>
    run?.scores?.scores?.find((s: any) => s.index === i);

  return (
    <>
      <PageTitle title="整本故事弧预测"
        subtitle="预测「从下一章一路到大结局」的完整剩余故事：先答主角真实身份 / 世界真相 / 幕后主谋 / 王朝命运等大问题，给出完整证据链与因果图，再设计阶段揭露顺序。每个候选都规划到结局" />

      <div className="card">
        <h2>触发预测</h2>
        <div className="row" style={{ alignItems: "center" }}>
          <label>起始章节<input type="number" value={after} onChange={(e) => setAfter(+e.target.value)} style={{ width: 100, marginLeft: 6 }} />
            {lastChapter != null && <span className="muted" style={{ fontSize: 11, marginLeft: 6 }}>（本书共 {lastChapter} 章）</span>}
          </label>
          <label>候选数<input type="number" value={n} onChange={(e) => setN(+e.target.value)} style={{ width: 70, marginLeft: 6 }} min={1} max={4} /></label>
          <label title="不是「写到第几章为止」——故事弧永远规划到结局；这里只是「用大约多少章把整本剩余故事讲完」的节奏/篇幅软提示，模型可能按自估章数微调">目标延展章节（到结局的篇幅）<input type="number" value={target} onChange={(e) => setTarget(+e.target.value)} style={{ width: 90, marginLeft: 6 }} min={20} max={500} /></label>
          {recommend && (
            <span style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12 }}>
              <span className="muted" title="往后再续写的章数（增量），不是写到第几章">💡 建议再写 <b style={{ color: "var(--accent-2)" }}>~{recommend.recommended}</b> 章（{recommend.low}–{recommend.high}，约到第 {recommend.end_at} 章）</span>
              <button onClick={() => setTarget(recommend.recommended)} className="ghost"
                style={{ padding: "2px 8px", fontSize: 11 }} disabled={target === recommend.recommended}>
                采用
              </button>
            </span>
          )}
        </div>
        {recommend && (
          <p className="muted" style={{ fontSize: 11, marginTop: 6 }}>{recommend.rationale}</p>
        )}

        <div style={{ marginTop: 10, display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <span style={{ fontSize: 13 }}>生成方式</span>
          <label style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 13, cursor: "pointer" }}>
            <input type="radio" name="arc-gen" checked={perCandidate} onChange={() => setPerCandidate(true)} />
            逐个生成
          </label>
          <label style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 13, cursor: "pointer" }}>
            <input type="radio" name="arc-gen" checked={!perCandidate} onChange={() => setPerCandidate(false)} />
            一起生成
          </label>
          <span className="muted" style={{ fontSize: 11 }}>
            {perCandidate
              ? "每次只产 1 个候选、逐个累计——章节较长 / 记忆量大时更稳（不易写崩成碎片）。"
              : "一次性产出全部候选——章节较短 / 记忆量小时更快（省一轮调用），长章慎用。"}
          </span>
        </div>

        <h3 style={{ marginTop: 16, marginBottom: 6 }}>创作偏好（可选）</h3>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 8 }}>
          {HINT_PRESETS.map((p) => {
            const active = hints.includes(p.text);
            return (
              <button key={p.label} onClick={() => togglePreset(p.text)}
                className={active ? "" : "ghost"}
                style={{ padding: "4px 10px", fontSize: 12 }} title={p.text}>
                {active ? "✓ " : "+ "}{p.label}
              </button>
            );
          })}
        </div>
        <textarea value={hints} onChange={(e) => setHints(e.target.value)} rows={4}
          placeholder="…（每行一条更清晰）"
          style={{ width: "100%", background: "var(--panel-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 6, padding: 10, fontFamily: "inherit", fontSize: 13, resize: "vertical" }} />

        <div style={{ marginTop: 12, display: "flex", alignItems: "center", gap: 12 }}>
          <button onClick={trigger} disabled={busy}>
            {busy ? `运行中… ${elapsed}s` : "运行"}
          </button>
          {busy && (
            <span className="muted" style={{ fontSize: 12 }}>
              新 schema 输出量大，预计 60–150 秒。两阶段（A 发散 → B 校验）依次完成。
            </span>
          )}
        </div>

        {run && (
          <>
            <p className="muted" style={{ marginTop: 8 }}>
              本次花费 ${run.cost_usd?.toFixed(4)} · winner: 候选 #{winnerIdx}
              {run.scores?.winner_reason && <> — {run.scores.winner_reason.slice(0, 140)}</>}
            </p>
            {run.user_hints && (
              <p className="muted" style={{ fontSize: 12, marginTop: 4, padding: "6px 10px", background: "var(--panel-2)", borderRadius: 4, borderLeft: "3px solid var(--accent-2)" }}>
                <strong>偏好：</strong> {run.user_hints}
              </p>
            )}
          </>
        )}
      </div>

      {run && Array.isArray(run.candidates) && run.candidates.length > 0 && (
        <WholeBookPanel runId={run.id} candidates={run.candidates} defaultIndex={winnerIdx ?? 0} />
      )}

      {run && (
        <div style={{ display: "grid", gap: 14 }}>
          {(Array.isArray(run.candidates) ? run.candidates : []).map((arc: any, i: number) => (
            <ArcCard key={i} idx={i} arc={arc} score={scoreOf(i)}
              arcRunId={run.id} chosenIndex={i}
              isWinner={i === winnerIdx} isOpen={openCard === i}
              onToggle={() => setOpenCard(openCard === i ? null : i)}
              outlineMap={outlineMap} onOutlineCreated={refreshOutlineMap} />
          ))}
        </div>
      )}

      <div className="card">
        <h2>历史预测</h2>
        <table>
          <thead><tr><th>id</th><th>从第几章</th><th>目标</th><th>偏好</th><th>winner</th><th>$</th><th>时间</th><th></th></tr></thead>
          <tbody>
            {history.map((r) => (
              <tr key={r.id}>
                <td>{r.id}</td><td>{r.after_chapter}</td><td>{r.target_chapters}</td>
                <td className="muted" style={{ maxWidth: 280, fontSize: 12 }}>
                  {r.user_hints ? r.user_hints.slice(0, 60) + (r.user_hints.length > 60 ? "…" : "") : "—"}
                </td>
                <td>#{r.chosen_index}</td><td>${r.cost_usd?.toFixed(4)}</td>
                <td className="muted">{r.created_at?.replace("T", " ").slice(0, 19)}</td>
                <td style={{ whiteSpace: "nowrap" }}>
                  <button onClick={() => loadHistory(r.id)} className="ghost" style={{ padding: "4px 8px", fontSize: 12, marginRight: 4 }}>查看</button>
                  <button onClick={() => loadFromHistory(r)} className="ghost" style={{ padding: "4px 8px", fontSize: 12 }}>复用</button>
                </td>
              </tr>
            ))}
            {history.length === 0 && <tr><td colSpan={8} className="muted">暂无</td></tr>}
          </tbody>
        </table>
      </div>

      {err && <div className="card" style={{ borderColor: "var(--bad)" }}>错误：{err}</div>}
    </>
  );
}

// ---------------------------------------------------------------------------

function ArcCard({ arc, idx, score, arcRunId, chosenIndex, isWinner, isOpen, onToggle,
                   outlineMap, onOutlineCreated }: {
  arc: any; idx: number; score: any; arcRunId: number; chosenIndex: number;
  isWinner: boolean; isOpen: boolean; onToggle: () => void;
  outlineMap: Map<string, number>;
  onOutlineCreated: () => void;
}) {
  const router = useRouter();
  const [refining, setRefining] = useState<number | null>(null);

  const outlineIdFor = (phaseIndex: number): number | undefined =>
    outlineMap.get(`arc|${arcRunId}|${chosenIndex}|${phaseIndex}`);

  const refinePhase = async (phaseIndex: number, mode: "oneshot" | "stepwise" = "oneshot") => {
    setRefining(phaseIndex);
    try {
      const r = await api.outlineRefine({
        source_kind: "arc",
        source_run_id: arcRunId,
        chosen_index: chosenIndex,
        phase_index: phaseIndex,
        mode,
      });
      onOutlineCreated();
      router.push(`/outline?id=${r.id}`);
    } catch (e: any) {
      alert("失败：" + e);
    } finally {
      setRefining(null);
    }
  };
  const phases = Array.isArray(arc?.phases) ? arc.phases : [];
  const truths = Array.isArray(arc?.core_truths) ? arc.core_truths : [];
  const fates = Array.isArray(arc?.faction_fates) ? arc.faction_fates : [];
  const graph = arc?.causal_graph || { nodes: [], edges: [] };

  return (
    <div className="card" style={{
      borderColor: isWinner ? "var(--accent-2)" : "var(--border)",
      background: isWinner ? "rgba(187,154,247,.05)" : undefined,
    }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
        <div>
          <h2 style={{ margin: 0 }}>
            #{idx} {arc?.title}
            {isWinner && <span className="tag" style={{ background: "var(--accent-2)", color: "#0e1015", marginLeft: 8 }}>WINNER</span>}
          </h2>
          <p className="muted" style={{ margin: "4px 0 0", fontSize: 12 }}>{arc?.theme}</p>
          <p style={{ margin: "4px 0 0", fontSize: 12 }}>
            <span className="tag">{arc?.tone}</span>
            <span className="tag">~{arc?.total_chapters_estimated} 章</span>
            <span className="tag">{phases.length} 阶段</span>
            <span className="tag">{truths.length} 真相</span>
            <span className="tag">{fates.length} 势力定型</span>
            <span className="tag">{(graph.nodes || []).length} 因果节点</span>
          </p>
        </div>
        <button onClick={onToggle} className="ghost" style={{ padding: "4px 12px", fontSize: 12 }}>
          {isOpen ? "收起" : "展开"}
        </button>
      </div>

      {isOpen && (
        <>
          {/* 三大底牌：主角真相 / 世界真相 / 幕后主谋 */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10, marginTop: 14 }}>
            <PrimaryPanel title="主角真实身份" color="#bb9af7">
              <strong>{arc?.protagonist_truth?.true_identity}</strong>
              <p className="muted" style={{ margin: "4px 0 0", fontSize: 12 }}>来历：{arc?.protagonist_truth?.origin}</p>
              <p className="muted" style={{ margin: "2px 0 0", fontSize: 12 }}>终极角色：{arc?.protagonist_truth?.ultimate_role}</p>
            </PrimaryPanel>
            <PrimaryPanel title="世界真相" color="#7aa2f7">
              <p style={{ margin: 0, fontSize: 13 }}>{arc?.world_truth}</p>
            </PrimaryPanel>
            <PrimaryPanel title="幕后主谋" color="#f7768e">
              <strong>{arc?.ultimate_mastermind?.identity}</strong>
              <p className="muted" style={{ margin: "4px 0 0", fontSize: 12 }}>动机：{arc?.ultimate_mastermind?.motive}</p>
              {arc?.ultimate_mastermind?.method && <p className="muted" style={{ margin: "2px 0 0", fontSize: 12 }}>方法：{arc.ultimate_mastermind.method}</p>}
              {arc?.ultimate_mastermind?.first_hint_chapter && <p className="muted" style={{ margin: "2px 0 0", fontSize: 11 }}>首次暗示：第 {arc.ultimate_mastermind.first_hint_chapter} 章</p>}
            </PrimaryPanel>
          </div>

          {/* 核心真相列表 */}
          {truths.length > 0 && (
            <>
              <h3 style={{ marginTop: 18 }}>核心真相 · {truths.length} 条</h3>
              <div style={{ display: "grid", gap: 10 }}>
                {truths.map((t: any, i: number) => (
                  <div key={i} style={{ background: "var(--panel-2)", borderRadius: 6, padding: 12, borderLeft: "3px solid #bb9af7" }}>
                    <div style={{ fontSize: 13, color: "#7aa2f7", marginBottom: 4 }}>Q{i + 1} · {t.question}</div>
                    <div style={{ marginBottom: 6 }}>{t.answer}</div>
                    {(t.evidence_chain || []).length > 0 && (
                      <ol style={{ margin: "6px 0 4px 18px", padding: 0, fontSize: 12, color: "var(--muted)" }}>
                        {t.evidence_chain.map((step: string, j: number) => <li key={j}>{step}</li>)}
                      </ol>
                    )}
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 6 }}>
                      {(t.related_foreshadow_ids || []).length > 0 && (
                        <span className="tag" style={{ background: "rgba(126,207,106,.15)", color: "#9ece6a" }}>
                          关联伏笔 #{t.related_foreshadow_ids.join(", #")}
                        </span>
                      )}
                      {t.revealed_in_phase_index != null && phases[t.revealed_in_phase_index] && (
                        <span className="tag">在阶段「{phases[t.revealed_in_phase_index]?.name}」揭晓</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}

          {/* 势力命运 */}
          {fates.length > 0 && (
            <>
              <h3 style={{ marginTop: 18 }}>势力命运 · {fates.length}</h3>
              <table>
                <thead><tr><th>势力</th><th>结局</th><th>根本原因</th><th>定型阶段</th></tr></thead>
                <tbody>
                  {fates.map((f: any, i: number) => (
                    <tr key={i}>
                      <td><strong>{f.name}</strong></td>
                      <td>{f.fate}</td>
                      <td className="muted" style={{ fontSize: 12 }}>{f.cause}</td>
                      <td className="muted">{f.phase_index != null && phases[f.phase_index] ? phases[f.phase_index].name : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}

          {/* 因果图（modern: React Flow + dagre / classic: echarts force） */}
          {graph.nodes?.length > 0 && <CausalGraphSection graph={graph} />}

          {/* 阶段时间线 + 详情 */}
          {phases.length > 0 && (
            <>
              <h3 style={{ marginTop: 18 }}>阶段时间线</h3>
              <PhaseGantt phases={phases} startChapter={phases[0]?.chapter_start || 1} />
              <h3 style={{ marginTop: 14 }}>阶段详情</h3>
              <div style={{ display: "grid", gap: 8 }}>
                {phases.map((p: any, i: number) => (
                  <div key={i} style={{
                    background: "var(--panel-2)", borderRadius: 6, padding: 10,
                    borderLeft: `3px solid ${PHASE_COLORS[i % PHASE_COLORS.length]}`,
                  }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 6 }}>
                      <strong>{p.name}</strong>
                      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                        <span className="muted" style={{ fontSize: 12 }}>第 {p.chapter_start}–{p.chapter_end} 章</span>
                        {(() => {
                          const existingId = outlineIdFor(i);
                          if (existingId !== undefined) {
                            return (
                              <Link
                                href={`/outline?id=${existingId}`}
                                style={{
                                  padding: "3px 10px",
                                  fontSize: 11,
                                  background: "rgba(126,207,106,.15)",
                                  border: "1px solid var(--good)",
                                  color: "var(--good)",
                                  borderRadius: 4,
                                  textDecoration: "none",
                                  fontWeight: 600,
                                }}
                              >
                                ✓ 已细化 → 大纲 #{existingId}
                              </Link>
                            );
                          }
                          return (
                            <span style={{ display: "inline-flex", gap: 4 }}>
                              <button onClick={() => refinePhase(i, "oneshot")} disabled={refining !== null}
                                className="ghost" style={{ padding: "3px 8px", fontSize: 11 }}
                                title="一次性产出整段——快、省额度">
                                {refining === i ? "生成中…" : "→ 细化大纲"}
                              </button>
                              <button onClick={() => refinePhase(i, "stepwise")} disabled={refining !== null}
                                className="ghost" style={{ padding: "3px 8px", fontSize: 11 }}
                                title="骨架+填充逐章——细节更厚、承接更稳,但更慢更耗额度">
                                {refining === i ? "…" : "⊕ 骨架+填充"}
                              </button>
                            </span>
                          );
                        })()}
                      </div>
                    </div>
                    {p.core_truth_revealed && (
                      <p style={{ margin: "4px 0 4px", fontSize: 12, color: "#bb9af7" }}>
                        ↪ 揭晓真相：{p.core_truth_revealed}
                      </p>
                    )}
                    <p style={{ margin: "4px 0 0" }}>{p.summary}</p>
                    {(p.key_events || []).length > 0 && (
                      <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
                        {p.key_events.map((ev: string, j: number) => <li key={j} style={{ fontSize: 13 }}>{ev}</li>)}
                      </ul>
                    )}
                    <div style={{ marginTop: 6, display: "flex", gap: 6, flexWrap: "wrap" }}>
                      {p.hero_arc_change && <span className="tag" style={{ background: "rgba(187,154,247,.15)", color: "#bb9af7" }}>主角: {p.hero_arc_change}</span>}
                      {p.stakes && <span className="tag" style={{ background: "rgba(247,118,142,.15)", color: "#f7768e" }}>张力: {p.stakes}</span>}
                      {(p.foreshadow_ids_addressed || []).length > 0 && (
                        <span className="tag" style={{ background: "rgba(126,207,106,.15)", color: "#9ece6a" }}>
                          收束伏笔 #{p.foreshadow_ids_addressed.join(", #")}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}

          {arc?.climax_synopsis && (
            <>
              <h3 style={{ marginTop: 18 }}>高潮</h3>
              <p style={{ background: "var(--panel-2)", padding: 12, borderRadius: 6, lineHeight: 1.7 }}>{arc.climax_synopsis}</p>
            </>
          )}
          {arc?.ending && (
            <>
              <h3 style={{ marginTop: 14 }}>结局</h3>
              <p style={{ background: "var(--panel-2)", padding: 12, borderRadius: 6, lineHeight: 1.7 }}>{arc.ending}</p>
            </>
          )}

          {(score?.risks || []).length > 0 && (
            <p className="muted" style={{ marginTop: 12, fontSize: 12 }}>
              <strong>风险点：</strong>{score.risks.join("； ")}
            </p>
          )}
          {score && (
            <p className="muted" style={{ fontSize: 12, marginTop: 6 }}>
              <strong>评分：</strong>
              宏观自洽 {score.macro_coherence ?? "?"} · 证据 {score.evidence_quality ?? "?"} · 伏笔 {score.foreshadow_coverage ?? "?"} · 主角 {score.hero_arc ?? "?"} · 新鲜 {score.novelty ?? "?"}
            </p>
          )}
          {score?.verdict && <p className="muted" style={{ fontSize: 12 }}><strong>裁定：</strong>{score.verdict}</p>}
        </>
      )}
    </div>
  );
}

function PrimaryPanel({ title, color, children }: { title: string; color: string; children: React.ReactNode }) {
  return (
    <div style={{ background: "var(--panel-2)", borderRadius: 6, padding: 10, borderTop: `3px solid ${color}` }}>
      <div style={{ fontSize: 11, color, fontWeight: 600, letterSpacing: 1 }}>{title.toUpperCase()}</div>
      <div style={{ marginTop: 6, fontSize: 13, lineHeight: 1.55 }}>{children}</div>
    </div>
  );
}

// ---------------------------------------------------------------------------

function CausalGraphSection({ graph }: { graph: any }) {
  const { theme } = useTheme();
  return (
    <>
      <h3 style={{ marginTop: 18 }}>
        因果图 · {graph.nodes.length} 节点 / {(graph.edges || []).length} 边
        {theme === "modern" && " — 点击节点查看详情"}
      </h3>
      {theme === "modern" ? (
        <CausalFlowGraph graph={graph} height={520} />
      ) : (
        <ClassicCausalGraph graph={graph} />
      )}
    </>
  );
}

function ClassicCausalGraph({ graph }: { graph: any }) {
  const { colorScheme } = useTheme();
  const ref = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (!ref.current) return;
    let chart: any;
    (async () => {
      const echarts = await import("echarts");
      chart = echarts.init(ref.current!);
      const pal = chartPalette();
      const kinds = ["origin", "truth", "agent", "event", "consequence"];
      const sizeByKind: Record<string, number> = { origin: 56, truth: 44, agent: 38, event: 32, consequence: 36 };
      chart.setOption({
        backgroundColor: "transparent",
        tooltip: {
          backgroundColor: pal.panel, borderColor: pal.border, textStyle: { color: pal.text },
          formatter: (p: any) => p.dataType === "node"
            ? `<b style="color:${KIND_COLORS[p.data.kind] || pal.text}">[${KIND_LABEL[p.data.kind] || p.data.kind}]</b> ${p.data.fullLabel}<br/>${p.data.description ? `<div style="max-width:380px;white-space:normal;margin-top:4px">${p.data.description}</div>` : ""}`
            : `${p.data.relation || ""}`,
        },
        legend: [{ data: kinds.map((k) => KIND_LABEL[k]), textStyle: { color: pal.text }, top: 4 }],
        series: [{
          type: "graph", layout: "force", roam: true, draggable: true, symbol: "circle",
          edgeSymbol: ["none", "arrow"], edgeSymbolSize: 8,
          label: { show: true, position: "right", color: pal.text, fontSize: 11, formatter: (p: any) => p.data.label },
          edgeLabel: { show: true, fontSize: 10, color: pal.muted, formatter: (p: any) => p.data.relation || "" },
          force: { repulsion: 320, edgeLength: [80, 160], gravity: 0.08 },
          categories: kinds.map((k) => ({ name: KIND_LABEL[k], itemStyle: { color: KIND_COLORS[k] } })),
          data: (graph.nodes || []).map((n: any) => ({
            id: n.id, name: n.id, label: n.label, fullLabel: n.label,
            description: n.description, kind: n.kind, category: kinds.indexOf(n.kind),
            symbolSize: sizeByKind[n.kind] || 30, itemStyle: { color: KIND_COLORS[n.kind] || pal.muted },
          })),
          links: (graph.edges || []).map((e: any) => ({
            source: e.from, target: e.to, relation: e.relation,
            lineStyle: { color: pal.border, curveness: 0.15 },
          })),
        }],
      });
      const handle = () => chart.resize();
      window.addEventListener("resize", handle);
      chart.__cleanup = () => window.removeEventListener("resize", handle);
    })();
    return () => { chart?.__cleanup?.(); chart?.dispose(); };
  }, [graph, colorScheme]);
  return <div ref={ref} style={{ width: "100%", height: 480, background: "var(--panel-2)", borderRadius: 6 }} />;
}

// ---------------------------------------------------------------------------

function PhaseGantt({ phases, startChapter }: { phases: any[]; startChapter: number }) {
  const { colorScheme } = useTheme();
  const ref = useRef<HTMLDivElement | null>(null);
  const lastEnd = phases.length > 0 ? Math.max(...phases.map((p: any) => p.chapter_end || 0)) : startChapter + 100;

  useEffect(() => {
    if (!ref.current || phases.length === 0) return;
    let chart: any;
    (async () => {
      const echarts = await import("echarts");
      chart = echarts.init(ref.current!);
      const pal = chartPalette();
      const labelFill = colorScheme === "light" ? "#fff" : "#0e1015";
      const data = phases.map((p: any, i: number) => ({
        value: [i, p.chapter_start, p.chapter_end, p.name, p.summary || "", (p.foreshadow_ids_addressed || []).join(",")],
        itemStyle: { color: PHASE_COLORS[i % PHASE_COLORS.length] },
      }));
      const renderItem = (params: any, apiObj: any) => {
        const idx = apiObj.value(0);
        const start = apiObj.coord([apiObj.value(1), idx]);
        const end = apiObj.coord([apiObj.value(2), idx]);
        const height = apiObj.size([0, 1])[1] * 0.7;
        return {
          type: "group",
          children: [
            { type: "rect", shape: { x: start[0], y: start[1] - height / 2, width: Math.max(end[0] - start[0], 4), height }, style: apiObj.style() },
            { type: "text", style: { text: apiObj.value(3), x: start[0] + 6, y: start[1], fill: labelFill, font: "600 12px system-ui", textVerticalAlign: "middle" } },
          ],
        };
      };
      chart.setOption({
        backgroundColor: "transparent",
        tooltip: {
          formatter: (p: any) => {
            const v = p.value;
            return `<b>[${v[3]}] ch${v[1]}-${v[2]}</b><br/>
                    <div style="max-width:480px;white-space:normal;margin-top:4px">${v[4]}</div>
                    ${v[5] ? `<div style="margin-top:6px;color:${pal.accent2};font-size:11px">收束伏笔: ${v[5]}</div>` : ""}`;
          },
          backgroundColor: pal.panel, borderColor: pal.border, textStyle: { color: pal.text },
        },
        grid: { left: 50, right: 16, top: 10, bottom: 28 },
        xAxis: {
          type: "value", name: "章节", min: startChapter, max: lastEnd,
          axisLabel: { color: pal.muted, fontSize: 10 },
          splitLine: { lineStyle: { color: pal.border } },
        },
        yAxis: {
          type: "value", inverse: true, min: -0.5, max: phases.length - 0.5,
          axisLabel: { show: false }, splitLine: { show: false }, axisTick: { show: false },
        },
        series: [{ type: "custom", renderItem, encode: { x: [1, 2], y: 0 }, data }],
      });
    })();
    return () => { chart?.dispose(); };
  }, [phases, lastEnd, startChapter, colorScheme]);

  return <div ref={ref} style={{ width: "100%", height: Math.max(phases.length * 30 + 50, 100), background: "var(--panel-2)", borderRadius: 6 }} />;
}

// ---------------------------------------------------------------------------
// 整本故事弧推演: expand the chosen arc's phases into a whole-book outline.
// ---------------------------------------------------------------------------
function WholeBookPanel({ runId, candidates, defaultIndex }: { runId: number; candidates: any[]; defaultIndex: number }) {
  const [idx, setIdx] = useState(defaultIndex);
  const [job, setJob] = useState<any | null>(null);
  const [running, setRunning] = useState(false);
  const [bookJob, setBookJob] = useState<any | null>(null);
  const [bookRunning, setBookRunning] = useState(false);
  const [batch, setBatch] = useState(3);
  const [phaseGate, setPhaseGate] = useState(true);  // C · 每写完1阶段暂停复审

  useEffect(() => { setIdx(defaultIndex); }, [defaultIndex]);

  // 挂载/切换 arc 时,回读该 arc 最近一次已完成的整本推演,刷新后不丢失结果。
  useEffect(() => {
    let cancelled = false;
    api.projectionList().then((list) => {
      const mine = (list || []).filter((p: any) => p.arc_run_id === runId);
      if (!mine.length) return;
      mine.sort((a: any, b: any) => b.id - a.id);
      return api.projectionGet(mine[0].id).then((d) => { if (!cancelled) setJob(d); });
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [runId]);

  // B+C · 启动/续写整本书（阶段 gate 模式：写完 1 阶段→复审→人审通过再续）
  const startWriteBook = async () => {
    if (!job?.id) return;
    setBookRunning(true);
    try {
      const opts = phaseGate ? { max_phases: 1 } : { max_chapters: batch || null };
      const r = await api.writeBook(job.id, opts);
      let attempts = 0;
      const t = setInterval(async () => {
        attempts += 1;
        try {
          const d = await api.bookWriteGet(r.id);
          setBookJob(d);
          if (d.status !== "writing") { setBookRunning(false); clearInterval(t); return; }
        } catch { /* transient */ }
        if (attempts >= 480) { clearInterval(t); setBookRunning(false); }  // ~40 min cap
      }, 5000);
    } catch { setBookRunning(false); }
  };

  const [forking, setForking] = useState(false);
  // 当前书已有的分支(用于判断某候选弧是否已建过分支 → 按钮显示"已建"而非重复报错)。
  const [branchesOfBook, setBranchesOfBook] = useState<any[]>([]);
  const refreshBranches = () => api.booksList().then((d: any) => {
    const act = d?.active;
    setBranchesOfBook((d?.books || []).filter((b: any) => b.is_branch && b.parent_slug === act));
  }).catch(() => {});
  useEffect(() => { refreshBranches(); }, []);
  // 当前选中候选弧是否已建分支:按 (arc_run_id, chosen_index) 精确匹配。
  const existingBranch = branchesOfBook.find((b) => b.arc_run_id === runId && b.chosen_index === idx);

  // 一个候选弧 = 一个分支:把当前书 fork 成一本派生"分支书",分支元数据记 arc_run_id+chosen_index。
  const forkAsBranch = async () => {
    const arc = candidates[idx] || {};
    const name = arc.title || `候选${idx}`;
    setForking(true);
    try {
      const bl = await api.booksList();
      const parent = bl?.active;
      if (!parent) { alert("没有当前书"); return; }
      if (!window.confirm(`把《${parent}》按候选弧「${name}」建成一个独立分支?\n(克隆原著记忆作基线;之后在分支里推演/续写,与原著及其它分支互不污染)`)) return;
      const r = await api.booksFork(parent, name, { arcRunId: runId, chosenIndex: idx, setActive: false });
      alert(`已建分支「${r.branch_name}」(基线 ${r.base_chapter} 章)。到书架切换到它即可在分支里推演/续写。`);
      await refreshBranches();
    } catch (e: any) {
      alert("建分支失败:" + (e?.message || e));
    } finally {
      setForking(false);
    }
  };

  const project = async () => {
    setRunning(true); setJob(null);
    try {
      const r = await api.arcProject(runId, idx);
      let attempts = 0;
      const t = setInterval(async () => {
        attempts += 1;
        try {
          const d = await api.projectionGet(r.id);
          setJob(d);
          if (d.status !== "projecting") { setRunning(false); clearInterval(t); return; }
        } catch { /* transient */ }
        if (attempts >= 240) { clearInterval(t); setRunning(false); }  // ~20 min cap
      }, 5000);
    } catch { setRunning(false); }
  };

  const v = job?.verdict || {};
  const chapters: any[] = job?.chapters || [];
  // group chapters by phase_name preserving order
  const groups: { name: string; chs: any[] }[] = [];
  for (const c of chapters) {
    const nm = c.phase_name || "—";
    let g = groups[groups.length - 1];
    if (!g || g.name !== nm) { g = { name: nm, chs: [] }; groups.push(g); }
    g.chs.push(c);
  }

  return (
    <div className="card" style={{ borderLeft: "4px solid var(--accent-2)" }}>
      <h2 style={{ marginTop: 0 }}>🌌 整本故事弧推演</h2>
      <p className="muted" style={{ marginTop: -4 }}>
        把选中的故事弧逐阶段展开成「从下一章到结局」的连续逐章大纲。骨架定全局、逐阶段重锚定、最后做完整性裁决。
      </p>
      <div className="row" style={{ alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <span className="muted">基于候选</span>
        <select value={idx} onChange={(e) => setIdx(Number(e.target.value))}
          style={{ padding: "5px 8px", borderRadius: 6, border: "1px solid var(--border)", background: "var(--panel)", color: "inherit", fontSize: 13 }}>
          {candidates.map((a: any, i: number) => (
            <option key={i} value={i}>#{i} {a.title || `候选${i}`}（{(a.phases || []).length} 阶段 · 估 {a.total_chapters_estimated ?? "?"} 章）</option>
          ))}
        </select>
        <button onClick={project} disabled={running} style={{ padding: "6px 16px" }}>
          {running ? `推演中…${job?.stage ? `（${job.stage}）` : ""}` : "🌌 推演整本书"}
        </button>
        {existingBranch ? (
          <button className="ghost" disabled style={{ padding: "6px 14px", opacity: 0.7, cursor: "default" }}
            title={`此候选弧已建分支「${existingBranch.branch_name || existingBranch.slug}」——到「书架」切换到它即可推演/续写。要重建请先在书架删掉旧分支。`}>
            ✓ 已建分支「{existingBranch.branch_name || existingBranch.slug}」
          </button>
        ) : (
          <button className="ghost" onClick={forkAsBranch} disabled={forking} style={{ padding: "6px 14px" }}
            title="把这个候选弧建成一本独立的分支书(克隆原著基线;分支内推演/续写与原著及其它分支隔离、可单独回滚)">
            {forking ? "建分支中…" : "🌿 把此候选弧建为分支"}
          </button>
        )}
        {job?.status === "failed" && <span style={{ color: "var(--bad)" }}>失败：{job.error}</span>}
      </div>

      {job?.status === "done" && (
        <div style={{ marginTop: 14 }}>
          <div className="row" style={{ gap: 16, flexWrap: "wrap", marginBottom: 10 }}>
            <span><strong style={{ color: "var(--accent-2)" }}>{job.arc_title}</strong></span>
            <span className="muted">体量：第 {job.after_chapter + 1}–{job.end_chapter} 章 · 共 {job.total_chapters} 章</span>
            <span className="tag" style={{ background: v.verdict === "pass" ? "var(--good)" : "var(--warn)", color: "#0e1015" }}>
              裁决：{v.verdict === "pass" ? "通过" : v.verdict || "—"}
            </span>
          </div>
          {/* completeness verdict */}
          <div className="card" style={{ background: "var(--panel-2)", marginBottom: 12 }}>
            {v.coverage_note && <p style={{ marginTop: 0, fontSize: 13 }}>{v.coverage_note}</p>}
            {(v.unresolved_truths || []).length > 0 && (
              <p style={{ fontSize: 12, color: "var(--warn)" }}>⚠ 未交代的关键问题：{v.unresolved_truths.join("；")}</p>
            )}
            {(v.coherence_issues || []).length > 0 && (
              <p style={{ fontSize: 12, color: "var(--warn)" }}>⚠ 连贯性问题：{v.coherence_issues.join("；")}</p>
            )}
            {(v.still_open_foreshadow_ids || []).length > 0 && (
              <p className="muted" style={{ fontSize: 12 }}>仍未收束伏笔 id：{v.still_open_foreshadow_ids.join(", ")}</p>
            )}
          </div>
          {/* B+C · 滚动地平线整本书写作 + 阶段 gate */}
          <div className="card" style={{ background: "var(--panel-2)", marginBottom: 12, borderLeft: "3px solid var(--good)" }}>
            <div className="row" style={{ alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              <strong style={{ fontSize: 13 }}>✍️ 写整本书</strong>
              <span className="muted" style={{ fontSize: 12 }}>逐章成稿 → 回灌记忆 → 下一章。每写完 1 阶段做跨章复审（连贯/伏笔燃尽/体量）并暂停待你审。</span>
              <label style={{ fontSize: 12, marginLeft: "auto", display: "inline-flex", alignItems: "center", gap: 4 }}>
                <input type="checkbox" checked={phaseGate} onChange={(e) => setPhaseGate(e.target.checked)} />
                阶段 gate（每阶段暂停）
              </label>
              {!phaseGate && (
                <label style={{ fontSize: 12 }}>一次写
                  <input type="number" value={batch} min={0} max={120}
                    onChange={(e) => setBatch(Math.max(0, +e.target.value || 0))}
                    style={{ width: 52, margin: "0 4px", padding: "3px 6px", borderRadius: 6, border: "1px solid var(--border)", background: "var(--panel)", color: "inherit" }} />
                  章
                </label>
              )}
              <button onClick={startWriteBook} disabled={bookRunning} style={{ padding: "5px 14px" }}>
                {bookRunning ? `写作中…${bookJob ? `（${bookJob.chapters_done}/${bookJob.chapters_total}·${bookJob.stage || ""}）` : ""}`
                  : (bookJob && bookJob.status === "paused" ? "✓ 审核通过，继续下一阶段"
                    : bookJob && bookJob.chapters_done > 0 ? "接着写" : "开始写整本书")}
              </button>
            </div>
            {bookJob && (
              <div className="muted" style={{ fontSize: 12, marginTop: 8 }}>
                进度 {bookJob.chapters_done}/{bookJob.chapters_total} · 状态 {bookJob.status}
                {(bookJob.log || []).length > 0 && (
                  <span> · 最近：{(bookJob.log || []).slice(-3).map((l: any) => `第${l.chapter}章(${l.status}${l.reingest === "done" ? "·回灌✓" : ""})`).join(" ")}</span>
                )}
              </div>
            )}
            {/* C · 阶段复审报告（人审 gate） */}
            {(bookJob?.phase_reviews || []).map((rv: any, ri: number) => (
              <div key={ri} style={{ marginTop: 10, padding: "8px 12px", borderRadius: 6, border: "1px solid var(--border)",
                background: "var(--panel)", borderLeft: `3px solid ${rv.verdict === "pass" ? "var(--good)" : "var(--warn)"}` }}>
                <div style={{ fontSize: 12.5, fontWeight: 600 }}>
                  阶段复审：{rv.phase_name || `OutlineRun ${rv.outline_run_id}`} ·
                  <span style={{ color: rv.verdict === "pass" ? "var(--good)" : "var(--warn)" }}> {rv.verdict}</span>
                </div>
                {(rv.continuity_issues || []).length > 0 && <div style={{ fontSize: 12, color: "var(--warn)", marginTop: 4 }}>⚠ 连贯：{rv.continuity_issues.join("；")}</div>}
                {(rv.repetition || []).length > 0 && <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 2 }}>重复：{rv.repetition.join("；")}</div>}
                {rv.pacing_note && <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 2 }}>节奏/体量：{rv.pacing_note}</div>}
                <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>
                  伏笔燃尽：收束 {(rv.foreshadow_resolved || []).length} · 计划未收 {(rv.foreshadow_missed || []).length}
                </div>
                {(rv.callback_suggestions || []).length > 0 && <div style={{ fontSize: 12, color: "var(--accent-2)", marginTop: 2 }}>💡 {rv.callback_suggestions.join("；")}</div>}
              </div>
            ))}
          </div>

          {/* full outline grouped by phase */}
          {groups.map((g, gi) => (
            <div key={gi} style={{ marginBottom: 12 }}>
              <div style={{ fontWeight: 600, fontSize: 13, margin: "6px 0", color: "var(--accent-2)" }}>
                {g.name} · 第 {g.chs[0]?.chapter_index}–{g.chs[g.chs.length - 1]?.chapter_index} 章
              </div>
              <div style={{ display: "grid", gap: 6 }}>
                {g.chs.map((c: any) => (
                  <div key={c.chapter_index} style={{ padding: "8px 10px", background: "var(--panel-2)", borderRadius: 6, fontSize: 13 }}>
                    <strong>第 {c.chapter_index} 章 · {c.title}</strong>
                    {(c.must_include || []).length > 0 && (
                      <div className="muted" style={{ fontSize: 12, marginTop: 3 }}>必含：{(c.must_include || []).join("；")}</div>
                    )}
                    {c.ending_hook && <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>钩子：{c.ending_hook}</div>}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
