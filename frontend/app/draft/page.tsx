"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Drawer } from "antd";
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
};

const LANE_COLOR: Record<string, string> = {
  style: "#7aa2f7",
  plot: "#bb9af7",
  consistency: "#e0af68",
};

const SEVERITY_COLOR: Record<string, string> = {
  blocker: "var(--bad)",
  major: "var(--warn)",
  minor: "var(--muted)",
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

  const reload = () => api.draftList().then(setDrafts).catch(() => {});

  useEffect(() => { reload(); }, []);

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

  const triggerWrite = async () => {
    if (!outlineRunId || !chapterIndex) return;
    setBusy(true);
    setBusySince(Date.now());
    setMsg("");
    setProgress({ attempt: 1, stage: "starting", reviewers_done: [] });

    // Poll the draft row every 1.5s while the pipeline runs.
    const poll = async () => {
      try {
        const list = await api.draftList();
        const row = list.find(
          (d: any) =>
            d.outline_run_id === Number(outlineRunId) &&
            d.chapter_index === Number(chapterIndex)
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
      const r = await api.draftWrite(Number(outlineRunId), Number(chapterIndex), {
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

  return (
    <>
      <PageTitle title="逐章成稿"
        subtitle="Writer 出稿 → 文风 / 剧情 / 一致性 三审并行 → Editor 仲裁返工，最多 3 轮 ReAct" />

      <div className="card">
        <h2>触发：写一个章节</h2>
        <div className="row" style={{ alignItems: "center", flexWrap: "wrap" }}>
          <label>OutlineRun id<input type="number" value={outlineRunId}
            onChange={(e) => setOutlineRunId(e.target.value)}
            style={{ width: 80, marginLeft: 6 }} /></label>
          <label>章节号<input type="number" value={chapterIndex}
            onChange={(e) => setChapterIndex(e.target.value)}
            style={{ width: 90, marginLeft: 6 }} /></label>
          <label>最多 attempts<input type="number" value={maxAttempts}
            onChange={(e) => setMaxAttempts(+e.target.value)}
            min={1} max={5} style={{ width: 60, marginLeft: 6 }} /></label>
          <label style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12 }}>
            <input type="checkbox" checked={skipReviews} onChange={(e) => setSkipReviews(e.target.checked)} />
            跳过审查（快迭代）
          </label>
        </div>
        <div style={{ marginTop: 10 }}>
          <button onClick={triggerWrite} disabled={busy || !outlineRunId || !chapterIndex}>
            {busy ? `写作中… ${elapsed}s` : skipReviews ? "写（跳过审查）" : "写（含审查）"}
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
          {drafts.length === 0 && <p className="muted">还没写过</p>}
          <div style={{ display: "flex", gap: 10, overflowX: "auto", paddingBottom: 12 }}>
            {drafts
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
                      {d.n_attempts} 轮 · ${d.cost_usd?.toFixed(4)}
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
            {drafts.length === 0 && <p className="muted">还没写过</p>}
            <div style={{ display: "grid", gap: 6 }}>
              {drafts.map((d) => (
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
                    {d.title} · {d.n_attempts} 轮 · ${d.cost_usd?.toFixed(4)}
                  </div>
                </button>
              ))}
            </div>
          </div>

          <div style={{ flex: 1, minWidth: 0 }}>
            {selected ? <DraftDetail draft={selected} outline={selectedOutline} onSave={reload} /> : (
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
        {selected && <DraftDetail draft={selected} outline={selectedOutline} onSave={reload} />}
      </Drawer>
    </>
  );
}

function DraftDetail({ draft, outline, onSave }: { draft: any; outline: any | null; onSave: () => void }) {
  const [editing, setEditing] = useState(false);
  const [textDraft, setTextDraft] = useState(draft.final_text || "");
  const [openAttempt, setOpenAttempt] = useState<number | null>(null);

  useEffect(() => { setTextDraft(draft.final_text || ""); }, [draft.id, draft.final_text]);

  const save = async () => {
    await api.draftPatchText(draft.id, textDraft);
    setEditing(false);
    onSave();
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
        </h2>
        <span className="muted" style={{ fontSize: 12 }}>
          {(draft.attempts || []).length} attempts · ${draft.cost_usd?.toFixed(4)}
        </span>
      </div>

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
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, marginBottom: 12 }}>
                {(["style", "plot", "consistency"] as const).map((lane) => {
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

            {/* editor */}
            {a.editor && (
              <div style={{ background: "var(--panel-2)", padding: 10, borderRadius: 6, marginBottom: 12, borderLeft: "3px solid var(--accent-2)" }}>
                <div style={{ fontSize: 11, fontWeight: 600, color: "var(--accent-2)", letterSpacing: 1 }}>EDITOR · {a.editor.decision}</div>
                {a.editor.rationale && <p className="muted" style={{ fontSize: 12, margin: "4px 0" }}>{a.editor.rationale}</p>}
                {a.editor.revision_brief && (
                  <p style={{ fontSize: 13, margin: "6px 0 0", whiteSpace: "pre-wrap" }}>{a.editor.revision_brief}</p>
                )}
              </div>
            )}

            {/* prose */}
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 }}>
                <strong style={{ fontSize: 13, color: "var(--muted)" }}>正文（attempt {a.attempt}）</strong>
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
