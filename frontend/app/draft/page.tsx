"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Drawer, message } from "antd";
import { api } from "@/lib/api";
import { useTheme } from "@/components/ThemeProvider";
import PageTitle from "@/components/PageTitle";

const STATUS_COLOR: Record<string, string> = {
  draft: "#8a92a3",
  writing: "#7aa2f7",
  reviewing: "#bb9af7",
  approved: "#9ece6a",
  shipped_with_warnings: "#e0af68",
  failed: "#f7768e",
};

const STATUS_LABEL: Record<string, string> = {
  draft: "草稿",
  writing: "写作中",
  reviewing: "审查中",
  approved: "已通过",
  shipped_with_warnings: "已发但有警告",
  failed: "失败",
};

const SEVERITY_LABEL: Record<string, string> = {
  blocker: "拦截",
  major: "重要",
  minor: "次要",
};

const LANE_LABEL: Record<string, string> = {
  style: "文风",
  plot: "剧情",
  consistency: "一致性",
  era_register: "时代语域",
};

const LANE_COLOR: Record<string, string> = {
  style: "#7aa2f7",
  plot: "#bb9af7",
  consistency: "#e0af68",
  era_register: "#f7768e",
};

const SEVERITY_COLOR: Record<string, string> = {
  blocker: "var(--bad)",
  major: "var(--warn)",
  minor: "var(--muted)",
};

const DECISION_LABEL: Record<string, string> = {
  approve: "通过",
  revise: "返工",
  ship_with_warnings: "带警告发布",
};

const DECISION_COLOR: Record<string, string> = {
  approve: "var(--good)",
  revise: "var(--warn)",
  ship_with_warnings: "#e0af68",
};

// Bilingual job granular-stage labels (backend BilingualDraft.stage)
const BI_STAGE_LABEL: Record<string, string> = {
  zh_draft: "写中文稿",
  en_recreate: "英文再创作",
  translate: "交叉互译",
  merge: "取长补短融合",
  done: "完成",
};

const selectStyle: React.CSSProperties = {
  minWidth: 220,
  maxWidth: 420,
  padding: "7px 10px",
  borderRadius: 6,
  border: "1px solid var(--border)",
  background: "var(--panel)",
  color: "inherit",
  fontSize: 13,
};

export default function DraftPage() {
  return (
    <Suspense fallback={<div className="card">加载中…</div>}>
      <DraftPageInner />
    </Suspense>
  );
}

function DraftPageInner() {
  const { theme } = useTheme();
  const router = useRouter();
  const search = useSearchParams();
  const initOutlineRunId = search?.get("outline_run_id");
  const initChapterIndex = search?.get("chapter_index");
  const initDraftId = search?.get("id");

  const [drafts, setDrafts] = useState<any[]>([]);
  const [selected, setSelected] = useState<any | null>(null);
  // Outline metadata cache for the currently selected draft (for breadcrumb).
  const [selectedOutline, setSelectedOutline] = useState<any | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [busySince, setBusySince] = useState<number | null>(null);
  const [, setTick] = useState(0);
  const [skipReviews, setSkipReviews] = useState(false);
  const [maxAttempts, setMaxAttempts] = useState(3);
  const [msg, setMsg] = useState("");

  // form
  const [outlineRunId, setOutlineRunId] = useState(initOutlineRunId || "");
  const [chapterIndex, setChapterIndex] = useState(initChapterIndex || "");
  // Dropdown data so the user never has to type raw IDs.
  const [outlineRuns, setOutlineRuns] = useState<any[]>([]);
  const [outlineChapters, setOutlineChapters] = useState<any[]>([]);

  const reload = () => api.draftList().then(setDrafts).catch(() => {});

  useEffect(() => { reload(); }, []);

  // Load outline runs for the picker.
  useEffect(() => {
    api.outlineList().then((runs: any[]) => setOutlineRuns(runs || [])).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Smart default: land on the outline of the most-recently-written chapter
  // (so freshly-written chapters show up without hunting the dropdown), falling
  // back to the newest outline run. Runs once, never overrides a user/URL choice.
  useEffect(() => {
    if (outlineRunId || !outlineRuns.length) return;
    let runId = outlineRuns[0].id;
    if (drafts.length) {
      const latest = [...drafts].sort((a, b) =>
        String(b.updated_at || "").localeCompare(String(a.updated_at || "")))[0];
      if (latest?.outline_run_id) runId = latest.outline_run_id;
    }
    setOutlineRunId(String(runId));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drafts, outlineRuns]);

  // When the chosen outline run changes, load its chapters and auto-pick the
  // first not-yet-drafted chapter (or the first chapter).
  useEffect(() => {
    if (!outlineRunId) { setOutlineChapters([]); return; }
    api.outlineGet(Number(outlineRunId)).then((run: any) => {
      const chs = run?.chapters || [];
      setOutlineChapters(chs);
      const draftedForRun = new Set(
        drafts.filter((d) => d.outline_run_id === Number(outlineRunId))
              .map((d) => d.chapter_index)
      );
      const cur = Number(chapterIndex);
      const stillValid = chs.some((c: any) => c.chapter_index === cur);
      if (!stillValid) {
        const firstUndrafted = chs.find((c: any) => !draftedForRun.has(c.chapter_index));
        const pick = firstUndrafted || chs[0];
        if (pick) setChapterIndex(String(pick.chapter_index));
      }
    }).catch(() => setOutlineChapters([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [outlineRunId, drafts]);

  // Deep-link: ?id=N takes precedence; falls back to ?outline_run_id&chapter_index lookup.
  useEffect(() => {
    if (initDraftId) {
      const id = Number(initDraftId);
      if (Number.isFinite(id)) {
        api.draftGet(id).then((d) => {
          setSelected(d);
          if (theme === "modern") setDrawerOpen(true);
        }).catch(() => {});
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Fetch outline metadata when selected draft changes (for breadcrumb).
  useEffect(() => {
    if (!selected?.outline_run_id) {
      setSelectedOutline(null);
      return;
    }
    api.outlineGet(selected.outline_run_id)
      .then(setSelectedOutline)
      .catch(() => setSelectedOutline(null));
  }, [selected?.outline_run_id]);

  // Sync URL with selected
  useEffect(() => {
    if (selected?.id) {
      router.replace(`/draft?id=${selected.id}`, { scroll: false });
    }
  }, [selected?.id, router]);

  useEffect(() => {
    if (!busy) return;
    const t = setInterval(() => setTick((x) => x + 1), 1000);
    return () => clearInterval(t);
  }, [busy]);

  // Real-time progress while a draft pipeline runs (polled from DB).
  const [progress, setProgress] = useState<{
    attempt: number;
    stage: string;
    reviewers_done: string[];
  } | null>(null);

  // Optional explicit (orId, chIdx) lets "重写本章" reuse this without relying
  // on the form-state values; defaults to the form selection.
  const triggerWrite = async (orArg?: number, chArg?: number) => {
    const orId = orArg ?? Number(outlineRunId);
    const chIdx = chArg ?? Number(chapterIndex);
    if (!orId || !chIdx) return;
    setBusy(true);
    setBusySince(Date.now());
    setMsg("");
    setProgress({ attempt: 1, stage: "starting", reviewers_done: [] });

    // Poll the draft row every 1.5s while the pipeline runs.
    const poll = async () => {
      try {
        const list = await api.draftList();
        const row = list.find(
          (d: any) => d.outline_run_id === orId && d.chapter_index === chIdx
        );
        if (!row) return;
        // Pull full detail to read attempts_json
        const d = await api.draftGet(row.id);
        const atts = d.attempts || [];
        const last = atts[atts.length - 1];
        if (last) {
          setProgress({
            attempt: last.attempt,
            stage: last.stage || (d.status || "writing"),
            reviewers_done: Object.keys(last.reviews || {}),
          });
        }
      } catch {}
    };
    const pollTimer = setInterval(poll, 1500);
    poll();   // immediate first tick

    try {
      const r = await api.draftWrite(orId, chIdx, {
        skip_reviews: skipReviews,
        max_attempts: maxAttempts,
      });
      setMsg(`✅ ${STATUS_LABEL[r.status] || r.status} · ${r.attempts.length} 轮 · $${r.cost_usd.toFixed(4)}`);
      await reload();
      const d = await api.draftGet(r.id);
      setSelected(d);
    } catch (e: any) {
      setMsg(String(e));
    } finally {
      clearInterval(pollTimer);
      setBusy(false);
      setBusySince(null);
      setProgress(null);
    }
  };

  const elapsed = busy && busySince ? Math.floor((Date.now() - busySince) / 1000) : 0;

  // Timeline/history must reflect the SELECTED outline only — otherwise drafts
  // from other outlines (e.g. a different arc/phase) leak into the list.
  const shownDrafts = outlineRunId
    ? drafts.filter((d) => d.outline_run_id === Number(outlineRunId))
    : drafts;

  return (
    <>
      <PageTitle title="逐章成稿"
        subtitle="Writer 出稿 → 文风 / 剧情 / 一致性 三审并行 → Editor 仲裁返工，最多 3 轮 ReAct" />

      <div className="card">
        <h2>写一个章节</h2>
        {outlineRuns.length === 0 ? (
          <p className="muted" style={{ fontSize: 13 }}>
            还没有大纲。先到 <Link href="/outline" style={{ color: "var(--accent)" }}>大纲</Link> 页面把某条预测/全弧细化成逐章大纲，再回来成稿。
          </p>
        ) : (
          <>
            <div className="row" style={{ alignItems: "flex-end", flexWrap: "wrap", gap: 14 }}>
              {/* Outline run picker */}
              <label style={{ fontSize: 12, color: "var(--muted)" }}>
                <div style={{ marginBottom: 4 }}>选大纲</div>
                <select value={outlineRunId} onChange={(e) => setOutlineRunId(e.target.value)}
                  style={{ ...selectStyle, minWidth: 360, maxWidth: 560 }}>
                  {outlineRuns.map((r) => {
                    const src = r.source_kind === "arc"
                      ? `全弧#${r.source_run_id}`
                      : `预测#${r.source_run_id}`;
                    const ph = r.phase_index != null ? `阶段${r.phase_index + 1}` : "";
                    return (
                      <option key={r.id} value={r.id}>
                        {src}{ph ? ` ${ph}` : ""} · {r.phase_name || "(未命名)"} · 第{r.chapter_start}-{r.chapter_end}章（{r.chapter_count}章）· 大纲#{r.id}
                      </option>
                    );
                  })}
                </select>
              </label>

              {/* Chapter picker */}
              <label style={{ fontSize: 12, color: "var(--muted)" }}>
                <div style={{ marginBottom: 4 }}>选章节</div>
                <select value={chapterIndex} onChange={(e) => setChapterIndex(e.target.value)}
                  style={selectStyle} disabled={outlineChapters.length === 0}>
                  {outlineChapters.map((c) => {
                    const done = drafts.some(
                      (d) => d.outline_run_id === Number(outlineRunId) && d.chapter_index === c.chapter_index
                    );
                    return (
                      <option key={c.chapter_index} value={c.chapter_index}>
                        {done ? "✓ " : ""}第{c.chapter_index}章 {c.title || "(无标题)"}
                      </option>
                    );
                  })}
                </select>
              </label>

              <label style={{ fontSize: 12, color: "var(--muted)" }}>
                <div style={{ marginBottom: 4 }}>最多返工</div>
                <input type="number" value={maxAttempts}
                  onChange={(e) => setMaxAttempts(+e.target.value)}
                  min={1} max={5} style={{ width: 64, padding: "7px 8px", borderRadius: 6, border: "1px solid var(--border)", background: "var(--panel)", color: "inherit" }} />
              </label>

              <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12, paddingBottom: 8 }}>
                <input type="checkbox" checked={skipReviews} onChange={(e) => setSkipReviews(e.target.checked)} />
                跳过审查（快迭代）
              </label>
            </div>

            {/* Selected-chapter preview so the user sees what they're about to write */}
            {(() => {
              const co = outlineChapters.find((c) => c.chapter_index === Number(chapterIndex));
              if (!co) return null;
              return (
                <div style={{ marginTop: 12, padding: "10px 14px", background: "var(--panel-2)", borderRadius: 8, borderLeft: "3px solid var(--c-foreshadow)" }}>
                  <div style={{ fontSize: 13, fontWeight: 600 }}>第{co.chapter_index}章 · {co.title || "(无标题)"}</div>
                  {co.intent && <p className="muted" style={{ fontSize: 12, margin: "4px 0 6px" }}>{co.intent}</p>}
                  <div style={{ display: "flex", gap: 14, flexWrap: "wrap", fontSize: 11, color: "var(--muted)" }}>
                    {co.must_include?.length ? <span>必含 {co.must_include.length} 条</span> : null}
                    {co.must_avoid?.length ? <span>必避 {co.must_avoid.length} 条</span> : null}
                    {co.pacing ? <span>节奏：{String(co.pacing).slice(0, 24)}</span> : null}
                    {co.word_target ? <span>目标 {co.word_target} 字</span> : null}
                  </div>
                </div>
              );
            })()}
          </>
        )}
        <div style={{ marginTop: 12 }}>
          <button onClick={() => triggerWrite()} disabled={busy || !outlineRunId || !chapterIndex}>
            {busy ? `写作中… ${elapsed}s` : skipReviews ? "✍️ 写（跳过审查）" : "✍️ 写（含审查）"}
          </button>
          <span className="muted" style={{ marginLeft: 12, fontSize: 12 }}>
            带审查约 60-180 秒；跳过审查约 30-60 秒
          </span>
        </div>
        {busy && progress && <PipelineStepper progress={progress} maxAttempts={maxAttempts} skipReviews={skipReviews} />}
        {msg && <p style={{ marginTop: 8, fontSize: 12, color: msg.startsWith("✅") ? "var(--good)" : "var(--bad)" }}>{msg}</p>}
      </div>

      {theme === "modern" ? (
        <div className="card">
          <h2>章节时间线 — 点击查看完整 prose 与审查反馈</h2>
          {shownDrafts.length === 0 && <p className="muted">这个大纲还没写过章节</p>}
          <div style={{ display: "flex", gap: 10, overflowX: "auto", paddingBottom: 12 }}>
            {shownDrafts
              .slice()
              .sort((a, b) => a.chapter_index - b.chapter_index)
              .map((d) => {
                const sc = STATUS_COLOR[d.status] || "#888";
                return (
                  <button key={d.id}
                    onClick={async () => {
                      const full = await api.draftGet(d.id);
                      setSelected(full);
                      setDrawerOpen(true);
                    }}
                    className="ghost"
                    style={{
                      flex: "0 0 200px", textAlign: "left", padding: 12,
                      borderTop: `3px solid ${sc}`,
                      background: "var(--panel-2)",
                      borderColor: "var(--border)",
                      borderRadius: 6,
                    }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                      <strong style={{ fontSize: 12, color: sc }}>第 {d.chapter_index} 章</strong>
                      <span className="tag" style={{
                        background: `${sc}25`, color: sc, fontSize: 10,
                      }}>{STATUS_LABEL[d.status] || d.status}</span>
                    </div>
                    <div className="prose-cn" style={{
                      fontSize: 13, marginTop: 6, fontWeight: 500,
                      whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
                    }}>
                      {d.title || "(无标题)"}
                    </div>
                    <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>
                      <span style={{ color: (d.chars ?? 0) === 0 ? "var(--bad)" : "var(--accent-2)", fontWeight: 600 }}>
                        {(d.chars ?? 0) === 0 ? "空章 0 字" : `${d.chars} 字`}
                      </span> · {d.n_attempts} 轮 · ${d.cost_usd?.toFixed(4)}
                    </div>
                  </button>
                );
              })}
          </div>
        </div>
      ) : (
        <div className="row" style={{ alignItems: "stretch", gap: 14 }}>
          <div className="card" style={{ flex: "0 0 280px", marginBottom: 0, maxHeight: 700, overflow: "auto" }}>
            <h2>历史成稿</h2>
            {shownDrafts.length === 0 && <p className="muted">这个大纲还没写过章节</p>}
            <div style={{ display: "grid", gap: 6 }}>
              {shownDrafts.map((d) => (
                <button key={d.id} onClick={async () => setSelected(await api.draftGet(d.id))}
                  className="ghost"
                  style={{
                    textAlign: "left", padding: 10, fontSize: 12,
                    borderColor: selected?.id === d.id ? "var(--accent-2)" : "var(--border)",
                    background: selected?.id === d.id ? "rgba(187,154,247,.06)" : undefined,
                  }}>
                  <div>
                    <strong>第 {d.chapter_index} 章</strong>
                    <span className="tag" style={{
                      marginLeft: 6, background: `${STATUS_COLOR[d.status] || "#888"}25`,
                      color: STATUS_COLOR[d.status] || "#888",
                    }}>
                      {STATUS_LABEL[d.status] || d.status}
                    </span>
                  </div>
                  <div className="muted" style={{ marginTop: 4, fontSize: 11 }}>
                    {d.title} · <span style={{ color: (d.chars ?? 0) === 0 ? "var(--bad)" : undefined, fontWeight: (d.chars ?? 0) === 0 ? 600 : 400 }}>
                      {(d.chars ?? 0) === 0 ? "空章 0 字" : `${d.chars} 字`}
                    </span> · {d.n_attempts} 轮</div>
                </button>
              ))}
            </div>
          </div>

          <div style={{ flex: 1, minWidth: 0 }}>
            {selected ? (
              <DraftDetail draft={selected} outline={selectedOutline} onSave={reload}
                busy={busy} onRegenerate={() => triggerWrite(selected.outline_run_id, selected.chapter_index)} />
            ) : (
              <div className="card muted">从左边选一个成稿查看</div>
            )}
          </div>
        </div>
      )}

      {/* Modern: drawer holds the detail view */}
      <Drawer
        title={selected ? `第 ${selected.chapter_index} 章 · ${selected.title || ""}` : ""}
        placement="right"
        width="60%"
        open={theme === "modern" && drawerOpen && !!selected}
        onClose={() => setDrawerOpen(false)}
        mask={false}
      >
        {selected && (
          <DraftDetail draft={selected} outline={selectedOutline} onSave={reload}
            busy={busy} onRegenerate={() => triggerWrite(selected.outline_run_id, selected.chapter_index)} />
        )}
      </Drawer>
    </>
  );
}

function DraftDetail({ draft, outline, onSave, busy, onRegenerate }: {
  draft: any; outline: any | null; onSave: () => void;
  busy?: boolean; onRegenerate?: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [textDraft, setTextDraft] = useState(draft.final_text || "");
  const [openAttempt, setOpenAttempt] = useState<number | null>(null);

  // Bilingual: find/generate an EN version for THIS chapter, toggle 中/英/对照.
  const [biJob, setBiJob] = useState<any | null>(null);
  const [biView, setBiView] = useState<"zh" | "en" | "both">("both");
  const [biRunning, setBiRunning] = useState(false);
  const [mimicOn, setMimicOn] = useState<boolean | null>(null);

  // 顾虑2 · 润色建议(落库 + 局部采纳 + 锚点失效检测)
  const [edits, setEdits] = useState<any[] | null>(null);
  const [baseChanged, setBaseChanged] = useState(false);
  const [accepted, setAccepted] = useState<Set<number>>(new Set());
  const [sugBusy, setSugBusy] = useState(false);
  // 打开章节时加载已存建议(刷新后仍在)，并实时重算锚点状态
  useEffect(() => {
    setEdits(null); setAccepted(new Set()); setBaseChanged(false);
    api.getSuggestions(draft.id).then((r) => {
      if (r.edits && r.edits.length) { setEdits(r.edits); setBaseChanged(!!r.base_changed); }
    }).catch(() => {});
  }, [draft.id]);
  const runSuggest = async () => {
    setSugBusy(true); setAccepted(new Set());
    try {
      const r = await api.suggestEdits(draft.id);
      setEdits(r.edits || []); setBaseChanged(!!r.base_changed);
    } catch (e) { message.error("出建议失败：" + String(e)); }
    finally { setSugBusy(false); }
  };
  const applyAccepted = async () => {
    if (!edits) return;
    const ids = edits.filter((e) => accepted.has(e.id) && e.applicable).map((e) => e.id);
    if (!ids.length) { message.info("未勾选任何可采纳的建议"); return; }
    setSugBusy(true);
    try {
      const r = await api.applyEdits(draft.id, ids);
      const failMsg = (r.failed && r.failed.length) ? `，${r.failed.length} 处锚点失效未应用` : "";
      message.success(`已采纳 ${r.applied} 处${failMsg}${r.en_stale ? "（英文版已过时，可重新生成）" : ""}`);
      setAccepted(new Set()); onSave();
      const rr = await api.getSuggestions(draft.id);  // 重载，刷新 applied/stale 状态
      setEdits(rr.edits || []); setBaseChanged(!!rr.base_changed);
    } catch (e) { message.error("应用失败：" + String(e)); }
    finally { setSugBusy(false); }
  };

  useEffect(() => { setTextDraft(draft.final_text || ""); }, [draft.id, draft.final_text]);
  useEffect(() => { api.styleGet().then((d: any) => setMimicOn(!!d?.mimic_enabled)).catch(() => {}); }, []);

  // Look for an existing bilingual job for this chapter.
  useEffect(() => {
    setBiJob(null);
    api.bilingualList().then((list) => {
      const m = (list || []).find((b: any) => b.chapter === draft.chapter_index && b.status === "done");
      if (m) api.bilingualGet(m.id).then(setBiJob).catch(() => {});
    }).catch(() => {});
  }, [draft.id, draft.chapter_index]);

  const save = async () => {
    await api.draftPatchText(draft.id, textDraft);
    setEditing(false);
    onSave();
  };

  const genBilingual = async () => {
    const co = (outline?.chapters || []).find((c: any) => c.chapter_index === draft.chapter_index);
    const brief = co
      ? `【本章意图】${co.intent || ""}\n【必须包含】${(co.must_include || []).join("；")}\n【节奏】${co.pacing || ""}\n【钩子】${co.ending_hook || ""}\n保持悬疑，遵循原作叙事节奏。`
      : `续写第${draft.chapter_index}章，承接前文，保持悬疑。`;
    setBiRunning(true);
    try {
      const r = await api.bilingualStart({ brief, after_chapter: draft.chapter_index - 1, chapter_n: draft.chapter_index });
      let attempts = 0;
      const MAX_ATTEMPTS = 240; // ~20 min @ 5s — minimax-m3 bilingual wall-time is ~13-15 min (slow 32000-token merges); cap so a stuck job can't poll forever
      const poll = setInterval(async () => {
        attempts += 1;
        try {
          const d = await api.bilingualGet(r.id);
          setBiJob(d); // update every tick so the live stage shows; final render gated on status below
          if (d.status !== "writing") { setBiRunning(false); clearInterval(poll); return; }
        } catch { /* transient — keep polling until the cap */ }
        if (attempts >= MAX_ATTEMPTS) {
          clearInterval(poll);
          setBiRunning(false);
          message.error("双语续写超时（>20 分钟），请到「文笔风格」页查看任务状态");
        }
      }, 5000);
    } catch (e) { setBiRunning(false); }
  };

  return (
    <div className="card" style={{ marginBottom: 0 }}>
      {/* breadcrumb chain */}
      {outline && (
        <Breadcrumb outline={outline} chapterIndex={draft.chapter_index} />
      )}

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 8 }}>
        <h2 style={{ margin: 0 }}>
          第 {draft.chapter_index} 章 · {draft.title}
          <span className="tag" style={{
            marginLeft: 8, background: `${STATUS_COLOR[draft.status] || "#888"}25`,
            color: STATUS_COLOR[draft.status] || "#888",
          }}>
            {STATUS_LABEL[draft.status] || draft.status}
          </span>
          {mimicOn != null && (
            <span className="tag" style={{
              marginLeft: 6, fontSize: 11,
              background: mimicOn ? "rgba(187,154,247,.15)" : "rgba(16,185,129,.12)",
              color: mimicOn ? "var(--accent-2)" : "var(--good)",
            }} title={mimicOn ? "本书已开启「模仿原作者文风」，本章按原作者笔法写" : "本章按默认网文笔法写（未开启仿写）"}>
              文风：{mimicOn ? "仿写原作者" : "网文"}
            </span>
          )}
        </h2>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span className="muted" style={{ fontSize: 12 }}>
            {(draft.attempts || []).length} 轮 · ${draft.cost_usd?.toFixed(4)}
          </span>
          {onRegenerate && (
            <button onClick={onRegenerate} disabled={busy}
              style={{ padding: "4px 12px", fontSize: 12 }}>
              {busy ? "写作中…" : "🔄 重写本章"}
            </button>
          )}
          <button onClick={runSuggest} disabled={sugBusy} className="ghost"
            title="扫描中文定稿，出『就地替换』建议(套路词/翻译腔/时代错置/文化语域)。不改原文，逐条采纳。已有建议时点此重新生成(会花额度)。"
            style={{ padding: "4px 12px", fontSize: 12 }}>
            {sugBusy ? "分析中…" : (edits && edits.length ? "🔄 重新生成建议" : "✍️ 出修改建议(不改原文)")}
          </button>
          <button onClick={() => {
            const title = `第${draft.chapter_index}章 ${draft.title || ""}`.trim();
            let body = `${title}\n\n【中文】\n\n${draft.final_text || ""}`;
            if (biJob?.status === "done" && biJob.final_en) {
              body += `\n\n${"=".repeat(40)}\n\n【English】\n\n${biJob.final_en}`;
            }
            const blob = new Blob([body], { type: "text/plain;charset=utf-8" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url; a.download = `${title}${biJob?.final_en ? "_中英" : ""}.txt`;
            a.click(); URL.revokeObjectURL(url);
          }} className="ghost" style={{ padding: "4px 12px", fontSize: 12 }}
            title="导出本章为 txt（有英文版则中英对照）">
            ⬇ 导出
          </button>
        </div>
      </div>

      {/* ---- Bilingual (中/英/对照) ---- */}
      <div style={{ marginTop: 12, padding: "10px 12px", background: "var(--panel-2)", borderRadius: 8, borderLeft: "3px solid var(--accent-2)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <strong style={{ fontSize: 13 }}>🌐 双语版本</strong>
          {biJob?.status === "done" && (
            <div style={{ display: "flex", gap: 4 }}>
              {(["zh", "both", "en"] as const).map((v) => (
                <button key={v} onClick={() => setBiView(v)} className={biView === v ? "" : "ghost"}
                  style={{ padding: "2px 10px", fontSize: 12 }}>
                  {v === "zh" ? "中文" : v === "en" ? "English" : "对照"}
                </button>
              ))}
            </div>
          )}
          {/* A·完整互译精修：始终可点（即便已有 B 的锚定双语）。会重跑「独立中英稿→互译→取长补短」，**两边都会被改写**。 */}
          <button onClick={genBilingual} disabled={biRunning} className="ghost"
            title="模式 A：独立中英稿→互译→editor 取长补短融合。中英都会被精修改写（中文不再锁定）。约 5-15 分钟。"
            style={{ padding: "3px 12px", fontSize: 12 }}>
            {biRunning
              ? `精修中…${BI_STAGE_LABEL[biJob?.stage] ? `（${BI_STAGE_LABEL[biJob?.stage]}）` : "（约 5-15 分钟）"}`
              : biJob?.status === "done" ? "🔁 完整互译精修（A·会改中英）" : "✨ 生成本章英文/双语版（A）"}
          </button>
          <span className="muted" style={{ fontSize: 11 }}>
            {biJob?.status === "done"
              ? "当前为 B·锚定生成（中文锁定、英文锚定）。点上方按钮可跑 A·取长补短融合（会改中英）。"
              : "A：独立中英稿→互译→取长补短融合 · 可在「文笔风格」页看过程"}
          </span>
        </div>
        {biJob?.status === "done" && (
          <div style={{ display: "grid", gridTemplateColumns: biView === "both" ? "1fr 1fr" : "1fr", gap: 12, marginTop: 10 }}>
            {(biView === "zh" || biView === "both") && (
              <pre style={{ whiteSpace: "pre-wrap", fontFamily: 'ui-serif, "PingFang SC", serif', fontSize: 13.5, lineHeight: 1.75, background: "var(--bg)", padding: 12, borderRadius: 6, margin: 0, maxHeight: 520, overflow: "auto" }}>{biJob.final_zh}</pre>
            )}
            {(biView === "en" || biView === "both") && (
              <pre style={{ whiteSpace: "pre-wrap", fontFamily: "Georgia, serif", fontSize: 13.5, lineHeight: 1.7, background: "var(--bg)", padding: 12, borderRadius: 6, margin: 0, maxHeight: 520, overflow: "auto" }}>{biJob.final_en}</pre>
            )}
          </div>
        )}
      </div>

      {/* 顾虑2 · 润色建议 diff（局部采纳，不改原文，直到点应用） */}
      {edits && (
        <div style={{ marginTop: 12, padding: "10px 12px", background: "var(--panel-2)", borderRadius: 8, borderLeft: "3px solid var(--good)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 8 }}>
            <strong style={{ fontSize: 13 }}>✍️ 修改建议</strong>
            <span className="muted" style={{ fontSize: 12 }}>{edits.length} 条 · 勾选要采纳的 · 不勾不改</span>
            <button onClick={() => setAccepted(new Set(edits.filter((e) => e.found).map((e) => e.id)))}
              className="ghost" style={{ padding: "2px 8px", fontSize: 11 }}>全选</button>
            <button onClick={() => setAccepted(new Set())} className="ghost" style={{ padding: "2px 8px", fontSize: 11 }}>清空</button>
            <button onClick={applyAccepted} disabled={sugBusy || accepted.size === 0}
              style={{ padding: "3px 12px", fontSize: 12 }}>
              {sugBusy ? "应用中…" : `✓ 应用已采纳（${accepted.size}）`}
            </button>
          </div>
          {baseChanged && (
            <p style={{ fontSize: 11.5, color: "var(--warn)", margin: "0 0 8px" }}>
              ⚠ 原文自生成建议后已被改动——失效的条目已标「锚点失效」、不可采纳;如需最新建议请重新「修改建议」。
            </p>
          )}
          {edits.length === 0 && <p className="muted" style={{ fontSize: 12 }}>未发现需修改处 👍</p>}
          <div style={{ display: "grid", gap: 8 }}>
            {edits.map((e) => {
              const done = e.status === "applied";
              const stale = e.stale || e.status === "stale";
              const ok = e.applicable && !done;
              return (
              <label key={e.id} style={{ display: "flex", gap: 10, alignItems: "flex-start", padding: 8, borderRadius: 6,
                background: done ? "rgba(158,206,106,.12)" : accepted.has(e.id) ? "rgba(158,206,106,.08)" : "var(--bg)",
                cursor: ok ? "pointer" : "not-allowed", opacity: ok ? 1 : 0.5 }}>
                <input type="checkbox" disabled={!ok} checked={accepted.has(e.id)}
                  onChange={(ev) => { const n = new Set(accepted); ev.target.checked ? n.add(e.id) : n.delete(e.id); setAccepted(n); }}
                  style={{ marginTop: 3 }} />
                <div style={{ flex: 1, minWidth: 0, fontSize: 12.5, lineHeight: 1.7 }}>
                  <div style={{ marginBottom: 2 }}>
                    <span className="tag" style={{ fontSize: 10, background: "var(--panel)", marginRight: 6 }}>{e.category}</span>
                    <span className="muted" style={{ fontSize: 11 }}>{e.reason}</span>
                    {done && <span style={{ color: "var(--good)", fontSize: 11, marginLeft: 6 }}>✓ 已采纳</span>}
                    {stale && <span style={{ color: "var(--bad)", fontSize: 11, marginLeft: 6 }}>⚠ 锚点失效（原文已改），不可应用</span>}
                    {e.ambiguous && ok && <span style={{ color: "var(--warn)", fontSize: 11, marginLeft: 6 }}>（正文多处匹配，应用改第一处）</span>}
                  </div>
                  <div style={{ fontFamily: 'ui-serif, "PingFang SC", serif' }}>
                    <span style={{ background: "rgba(247,118,142,.18)", textDecoration: "line-through", color: "var(--bad)" }}>{e.quote}</span>
                    <span style={{ margin: "0 6px", color: "var(--muted)" }}>→</span>
                    <span style={{ background: "rgba(158,206,106,.18)", color: "var(--good)" }}>{e.replacement}</span>
                  </div>
                </div>
              </label>
            ); })}
          </div>
        </div>
      )}

      {/* review-model legend so the semantics are clear */}
      {(draft.attempts || []).some((a: any) => a.reviews) && (
        <div className="muted" style={{ fontSize: 11, marginTop: 8, lineHeight: 1.6 }}>
          审查机制：<span style={{ color: LANE_COLOR.consistency }}>一致性</span> / <span style={{ color: LANE_COLOR.plot }}>剧情</span> 可触发返工（硬伤）；
          <span style={{ color: LANE_COLOR.style }}>文风</span> 仅供参考，永不触发返工——避免为迎合主观文风把文笔越改越拧巴。
        </div>
      )}

      {/* attempts timeline */}
      {(draft.attempts || []).length > 1 && (
        <div style={{ marginTop: 10, display: "flex", gap: 6 }}>
          {(draft.attempts || []).map((a: any) => (
            <button key={a.attempt}
              onClick={() => setOpenAttempt(openAttempt === a.attempt ? null : a.attempt)}
              className={openAttempt === a.attempt ? "" : "ghost"}
              style={{ padding: "4px 10px", fontSize: 12 }}>
              attempt {a.attempt} · {a.editor?.decision || "?"}
            </button>
          ))}
        </div>
      )}

      {/* prose & reviews */}
      {(draft.attempts || []).map((a: any) => {
        if (openAttempt && openAttempt !== a.attempt) return null;
        if (!openAttempt && a.attempt !== (draft.attempts || []).length) return null;
        return (
          <div key={a.attempt} style={{ marginTop: 14 }}>
            {/* reviewer issues */}
            {a.reviews && (
              <div style={{ display: "grid", gridTemplateColumns: `repeat(${["style","plot","consistency","era_register"].filter((l)=>a.reviews[l]).length || 3}, 1fr)`, gap: 8, marginBottom: 12 }}>
                {(["style", "plot", "consistency", "era_register"] as const).filter((lane) => a.reviews[lane]).map((lane) => {
                  const r = a.reviews[lane] || {};
                  const issues = r.issues || [];
                  return (
                    <div key={lane} style={{ background: "var(--panel-2)", padding: 10, borderRadius: 6, borderTop: `3px solid ${LANE_COLOR[lane]}` }}>
                      <div style={{ fontSize: 11, fontWeight: 600, color: LANE_COLOR[lane], letterSpacing: 1 }}>
                        {LANE_LABEL[lane].toUpperCase()} · {issues.length} ISSUE{issues.length === 1 ? "" : "S"}
                      </div>
                      <p className="muted" style={{ fontSize: 12, margin: "4px 0 6px" }}>{r.overall || ""}</p>
                      {issues.map((it: any, i: number) => (
                        <div key={i} style={{ marginTop: 6, paddingTop: 6, borderTop: "1px solid var(--border)" }}>
                          <span className="tag" style={{
                            background: `${SEVERITY_COLOR[it.severity] || "#888"}25`,
                            color: SEVERITY_COLOR[it.severity] || "#888",
                            fontSize: 10,
                          }}>{SEVERITY_LABEL[it.severity] || it.severity}</span>
                          {it.quote && (
                            <p style={{ fontSize: 12, margin: "4px 0", fontFamily: "ui-serif, serif", fontStyle: "italic" }}>「{it.quote}」</p>
                          )}
                          {it.suggestion && (
                            <p style={{ fontSize: 12, margin: "2px 0", color: "var(--good)" }}>→ {it.suggestion}</p>
                          )}
                          {it.reasoning && (
                            <p className="muted" style={{ fontSize: 11, margin: "2px 0" }}>{it.reasoning}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  );
                })}
              </div>
            )}

            {/* editor verdict */}
            {a.editor && (() => {
              const dec = a.editor.decision;
              const styleOnly =
                (a.reviews?.style?.issues?.length || 0) > 0 &&
                (a.reviews?.plot?.issues?.length || 0) === 0 &&
                (a.reviews?.consistency?.issues?.length || 0) === 0;
              return (
                <div style={{ background: "var(--panel-2)", padding: "10px 12px", borderRadius: 6, marginBottom: 12, borderLeft: `3px solid ${DECISION_COLOR[dec] || "var(--accent-2)"}` }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: 11, fontWeight: 600, color: "var(--muted)", letterSpacing: 1 }}>编辑裁决</span>
                    <span className="tag" style={{
                      background: `${DECISION_COLOR[dec] || "#888"}25`,
                      color: DECISION_COLOR[dec] || "#888", fontSize: 11, fontWeight: 600,
                    }}>{DECISION_LABEL[dec] || dec}</span>
                  </div>
                  {a.editor.rationale && <p className="muted" style={{ fontSize: 12, margin: "6px 0 0" }}>{a.editor.rationale}</p>}
                  {styleOnly && dec === "approve" && (
                    <p style={{ fontSize: 11, margin: "4px 0 0", color: "var(--good)" }}>
                      仅有文风建议——文风不触发返工，已直接通过。
                    </p>
                  )}
                  {a.editor.revision_brief && dec !== "approve" && (
                    <p style={{ fontSize: 13, margin: "6px 0 0", whiteSpace: "pre-wrap" }}>{a.editor.revision_brief}</p>
                  )}
                </div>
              );
            })()}

            {/* prose */}
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 }}>
                <strong style={{ fontSize: 13, color: "var(--muted)" }}>
                  正文（attempt {a.attempt}）
                  <span style={{ marginLeft: 8, color: "var(--accent-2)", fontWeight: 600 }}>
                    {(a.prose || "").replace(/\s/g, "").length} 字
                  </span>
                </strong>
                {a.attempt === (draft.attempts || []).length && (
                  editing ? (
                    <div style={{ display: "flex", gap: 6 }}>
                      <button onClick={save} style={{ padding: "4px 10px", fontSize: 12 }}>保存为最终稿</button>
                      <button onClick={() => { setEditing(false); setTextDraft(draft.final_text || ""); }}
                        className="ghost" style={{ padding: "4px 10px", fontSize: 12 }}>取消</button>
                    </div>
                  ) : (
                    <button onClick={() => setEditing(true)} className="ghost"
                      style={{ padding: "4px 10px", fontSize: 12 }}>手动编辑</button>
                  )
                )}
              </div>
              {editing && a.attempt === (draft.attempts || []).length ? (
                <textarea value={textDraft} onChange={(e) => setTextDraft(e.target.value)} rows={20}
                  style={{
                    width: "100%", background: "var(--panel-2)", color: "var(--text)",
                    border: "1px solid var(--border)", borderRadius: 6, padding: 12,
                    fontFamily: 'ui-serif, "PingFang SC", serif', fontSize: 14, lineHeight: 1.7,
                    resize: "vertical",
                  }} />
              ) : (
                <pre style={{
                  whiteSpace: "pre-wrap",
                  fontFamily: 'ui-serif, "PingFang SC", serif',
                  fontSize: 14, lineHeight: 1.75,
                  background: "var(--panel-2)", padding: 14, borderRadius: 6,
                  margin: 0, maxHeight: 600, overflow: "auto",
                }}>
                  {a.prose || ""}
                </pre>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// Maps backend stage strings to a 4-step display.
// Stages: "starting" | "writer" | "writer_done" | "reviewing" | "editor" | "done"
function PipelineStepper({
  progress, maxAttempts, skipReviews,
}: {
  progress: { attempt: number; stage: string; reviewers_done: string[] };
  maxAttempts: number;
  skipReviews: boolean;
}) {
  const { attempt, stage, reviewers_done } = progress;
  const steps = skipReviews
    ? [
        { key: "writer", label: "Writer 写稿" },
        { key: "done", label: "出稿" },
      ]
    : [
        { key: "writer", label: "Writer 写稿" },
        { key: "reviewing", label: `三审并行（${reviewers_done.length}/3）` },
        { key: "editor", label: "Editor 仲裁" },
        { key: "done", label: "完成本轮" },
      ];

  // active index based on stage
  const stageOrder = skipReviews
    ? ["starting", "writer", "writer_done", "done"]
    : ["starting", "writer", "writer_done", "reviewing", "editor", "done"];
  let activeIdx = stageOrder.indexOf(stage);
  if (activeIdx === -1) activeIdx = 0;
  // map stageOrder index to steps index
  const stepIdx = (() => {
    if (stage === "starting" || stage === "writer") return 0;
    if (stage === "writer_done") return skipReviews ? 1 : 1; // moving toward reviewing
    if (stage === "reviewing") return 1;
    if (stage === "editor") return 2;
    if (stage === "done") return steps.length - 1;
    return 0;
  })();

  return (
    <div style={{
      marginTop: 12,
      padding: "10px 14px",
      background: "var(--panel-2)",
      borderRadius: 8,
      borderLeft: "3px solid var(--accent)",
    }}>
      <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 8 }}>
        第 <strong style={{ color: "var(--accent-2)" }}>{attempt}</strong> / {maxAttempts} 轮
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 0 }}>
        {steps.map((s, i) => {
          const done = i < stepIdx;
          const active = i === stepIdx;
          return (
            <div key={s.key} style={{ display: "flex", alignItems: "center", flex: 1 }}>
              <div style={{
                width: 24, height: 24, borderRadius: 12,
                background: done ? "var(--good)" : active ? "var(--accent)" : "var(--panel)",
                border: `2px solid ${done ? "var(--good)" : active ? "var(--accent)" : "var(--border)"}`,
                color: done || active ? "#fff" : "var(--muted)",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 11, fontWeight: 600,
                flexShrink: 0,
                transition: "all 0.2s",
              }}>
                {done ? "✓" : i + 1}
              </div>
              <div style={{
                flex: 1,
                marginLeft: 8,
                fontSize: 12,
                color: done ? "var(--good)" : active ? "var(--text)" : "var(--muted)",
                fontWeight: active ? 600 : 400,
                whiteSpace: "nowrap",
              }}>
                {s.label}
                {active && <span style={{ marginLeft: 4 }}>···</span>}
              </div>
              {i < steps.length - 1 && (
                <div style={{
                  flex: 1,
                  height: 2,
                  background: done ? "var(--good)" : "var(--border)",
                  marginLeft: 8,
                  marginRight: 8,
                  minWidth: 20,
                }} />
              )}
            </div>
          );
        })}
      </div>
      {stage === "reviewing" && reviewers_done.length > 0 && (
        <div style={{ marginTop: 8, fontSize: 11, color: "var(--muted)" }}>
          已完成: {reviewers_done.map((r) => LANE_LABEL[r] || r).join(" · ")}
        </div>
      )}
    </div>
  );
}

function Breadcrumb({ outline, chapterIndex }: { outline: any; chapterIndex: number }) {
  const sourceHref =
    outline.source_kind === "arc"
      ? `/arc?id=${outline.source_run_id}&candidate=${outline.source_chosen_index ?? 0}`
      : `/predict?id=${outline.source_run_id}`;
  const sep = (
    <span style={{ color: "var(--muted)", margin: "0 6px", fontSize: 11 }}>▸</span>
  );
  const linkStyle = {
    fontSize: 12,
    color: "var(--accent)",
    textDecoration: "none",
  } as const;
  const crumbStyle = {
    fontSize: 12,
    color: "var(--muted)",
  } as const;
  return (
    <div style={{
      marginBottom: 12,
      padding: "6px 12px",
      background: "var(--panel-2)",
      borderRadius: 6,
      borderLeft: "3px solid var(--accent-2)",
      display: "flex",
      alignItems: "center",
      flexWrap: "wrap",
      gap: 2,
    }}>
      <Link href={sourceHref} style={linkStyle}>
        {outline.source_kind === "arc" ? "全弧" : "预测"} #{outline.source_run_id}
      </Link>
      {sep}
      <span style={crumbStyle}>候选 {outline.source_chosen_index ?? 0}</span>
      {sep}
      <span style={crumbStyle}>{outline.phase_name || `phase ${outline.phase_index ?? 0}`}</span>
      {sep}
      <Link href={`/outline?id=${outline.id}`} style={linkStyle}>
        大纲 #{outline.id}
      </Link>
      {sep}
      <span style={{ ...crumbStyle, color: "var(--accent-2)", fontWeight: 600 }}>
        第 {chapterIndex} 章
      </span>
    </div>
  );
}
