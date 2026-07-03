"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Tooltip } from "antd";
import { LeftOutlined, RightOutlined, HistoryOutlined } from "@ant-design/icons";
import { api } from "@/lib/api";
import ChapterFlowGraph from "@/components/ChapterFlowGraph";
import { useTheme } from "@/components/ThemeProvider";
import PageTitle from "@/components/PageTitle";

const SIDEBAR_KEY = "outline-sidebar-collapsed";
const FORM_KEY = "outline-form-collapsed";

export default function OutlinePage() {
  return (
    <Suspense fallback={<div className="card">加载中…</div>}>
      <OutlinePageInner />
    </Suspense>
  );
}

function OutlinePageInner() {
  const router = useRouter();
  const search = useSearchParams();
  const initId = search?.get("id");

  const [runs, setRuns] = useState<any[]>([]);
  const [arcRuns, setArcRuns] = useState<any[]>([]);
  const [selected, setSelected] = useState<any | null>(null);
  const [drafts, setDrafts] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [busySince, setBusySince] = useState<number | null>(null);
  const [, setTick] = useState(0);
  const [msg, setMsg] = useState("");

  // refine form state
  const [arcId, setArcId] = useState<number | "">("");
  const [chosenIdx, setChosenIdx] = useState(0);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [formCollapsed, setFormCollapsed] = useState(false);

  // 历史大纲跟随所选 ArcRun:只显示该 arc(source_kind=arc 且 source_run_id 匹配)下的大纲。
  const filteredRuns = useMemo(
    () => (arcId === "" ? [] : runs.filter((r) => r.source_kind === "arc" && r.source_run_id === Number(arcId))),
    [runs, arcId],
  );

  // Restore collapsed states from localStorage on mount.
  useEffect(() => {
    try {
      if (localStorage.getItem(SIDEBAR_KEY) === "1") setSidebarCollapsed(true);
      if (localStorage.getItem(FORM_KEY) === "1") setFormCollapsed(true);
    } catch {}
  }, []);
  const toggleForm = () => {
    setFormCollapsed((c) => {
      const next = !c;
      try { localStorage.setItem(FORM_KEY, next ? "1" : "0"); } catch {}
      return next;
    });
  };
  const toggleSidebar = () => {
    setSidebarCollapsed((c) => {
      const next = !c;
      try { localStorage.setItem(SIDEBAR_KEY, next ? "1" : "0"); } catch {}
      return next;
    });
  };
  const [phaseIdx, setPhaseIdx] = useState(0);
  const [hints, setHints] = useState("");
  const [mode, setMode] = useState<"oneshot" | "stepwise">("oneshot");

  const reload = () => api.outlineList().then(setRuns).catch(() => {});
  const reloadDrafts = () => api.draftList().then(setDrafts).catch(() => {});

  // Map: outline_run_id|chapter_index -> draft
  const draftMap = useMemo(() => {
    const m = new Map<string, any>();
    for (const d of drafts) {
      m.set(`${d.outline_run_id}|${d.chapter_index}`, d);
    }
    return m;
  }, [drafts]);

  useEffect(() => {
    reload();
    reloadDrafts();
    api.arcList().then(setArcRuns).catch(() => {});
  }, []);

  // Deep-link: load outline by ?id= once
  useEffect(() => {
    if (initId) {
      const id = Number(initId);
      if (Number.isFinite(id)) {
        api.outlineGet(id).then((d) => {
          setSelected(d);
          // 让左侧历史大纲列表跟随:深链进来的大纲若来自某 arc,自动选中该 arc。
          if (d?.source_kind === "arc" && d?.source_run_id != null) setArcId(Number(d.source_run_id));
        }).catch(() => {});
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Sync URL with selected
  useEffect(() => {
    if (selected?.id) {
      router.replace(`/outline?id=${selected.id}`, { scroll: false });
    }
  }, [selected?.id, router]);

  useEffect(() => {
    if (!busy) return;
    const t = setInterval(() => setTick((x) => x + 1), 1000);
    return () => clearInterval(t);
  }, [busy]);

  const refine = async () => {
    if (!arcId) return;
    setBusy(true);
    setBusySince(Date.now());
    setMsg("");
    try {
      const r = await api.outlineRefine({
        source_kind: "arc",
        source_run_id: Number(arcId),
        chosen_index: chosenIdx,
        phase_index: phaseIdx,
        user_hints: hints,
        mode,
      });
      await reload();
      setMsg(`✅ 生成 ${r.chapters?.length || 0} 章 · $${r.cost_usd?.toFixed(4)}`);
      const detail = await api.outlineGet(r.id);
      setSelected(detail);
    } catch (e: any) {
      setMsg(String(e));
    } finally {
      setBusy(false);
      setBusySince(null);
    }
  };

  const elapsed = busy && busySince ? Math.floor((Date.now() - busySince) / 1000) : 0;

  return (
    <>
      <PageTitle title="剧情大纲可视化" subtitle="从 arc winner 的某 phase 生成 5-15 章可执行大纲：意图 · 必含 · 必避 · 节奏 · 钩子" />

      <div className="card">
        {/* 表头始终可见:标题 + ArcRun 选择器(既是生成源,也是下方历史大纲的过滤器)+ 折叠开关 */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 10 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
            <h2 style={{ margin: 0, fontSize: 16 }}>触发：从 arc phase 生成大纲</h2>
            <label style={{ fontSize: 13 }}>
              ArcRun id
              <select value={arcId} onChange={(e) => setArcId(e.target.value === "" ? "" : Number(e.target.value))}
                style={{ marginLeft: 6 }}>
                <option value="">选一个</option>
                {arcRuns.map((r) => (
                  <option key={r.id} value={r.id}>
                    #{r.id} · ch{r.after_chapter} · winner #{r.chosen_index}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <button onClick={toggleForm} className="ghost" style={{ padding: "4px 12px", fontSize: 12 }}>
            {formCollapsed ? "展开生成表单 ▼" : "折叠 ▲"}
          </button>
        </div>

        {!formCollapsed && (
        <>
        <div className="row" style={{ alignItems: "center", flexWrap: "wrap", marginTop: 10 }}>
          <label>
            候选 idx
            <input type="number" value={chosenIdx} onChange={(e) => setChosenIdx(+e.target.value)}
              style={{ width: 60, marginLeft: 6 }} min={0} />
          </label>
          <label>
            Phase idx
            <input type="number" value={phaseIdx} onChange={(e) => setPhaseIdx(+e.target.value)}
              style={{ width: 60, marginLeft: 6 }} min={0} />
          </label>
        </div>
        <div style={{ marginTop: 10, display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <span style={{ fontSize: 13 }}>生成方式</span>
          <label style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 13, cursor: "pointer" }}>
            <input type="radio" name="outline-mode" checked={mode === "oneshot"} onChange={() => setMode("oneshot")} />
            一次性
          </label>
          <label style={{ display: "inline-flex", alignItems: "center", gap: 4, fontSize: 13, cursor: "pointer" }}>
            <input type="radio" name="outline-mode" checked={mode === "stepwise"} onChange={() => setMode("stepwise")} />
            骨架+填充
          </label>
          <span className="muted" style={{ fontSize: 11 }}>
            {mode === "oneshot"
              ? "一次调用产出整段章节——快、省额度;长 phase 易细节浅/前后矛盾。"
              : "先出整段骨架,再逐章展开(约 章数+1 次调用)——细节更厚、承接更稳,但更慢、更耗火山额度。"}
          </span>
        </div>
        <textarea value={hints} onChange={(e) => setHints(e.target.value)} rows={2}
          placeholder="（可选）创作偏好/导演备注…"
          style={{
            marginTop: 8, width: "100%", background: "var(--panel-2)", color: "var(--text)",
            border: "1px solid var(--border)", borderRadius: 6, padding: 8,
            fontFamily: "inherit", fontSize: 13, resize: "vertical",
          }} />
        <div style={{ marginTop: 10 }}>
          <button onClick={refine} disabled={busy || !arcId}>
            {busy ? `生成中… ${elapsed}s` : "生成大纲（约 30-60 秒）"}
          </button>
        </div>
        {msg && <p style={{ marginTop: 8, fontSize: 12, color: msg.startsWith("✅") ? "var(--good)" : "var(--bad)" }}>{msg}</p>}
        </>
        )}
      </div>

      <div style={{ display: "flex", alignItems: "stretch", gap: 14, transition: "all 200ms" }}>
        {/* 左：可折叠的历史大纲列表 */}
        <div className="card" style={{
          flex: sidebarCollapsed ? "0 0 44px" : "0 0 280px",
          marginBottom: 0,
          maxHeight: "calc(100vh - 240px)",
          overflow: "auto",
          padding: sidebarCollapsed ? 8 : "16px 20px",
          transition: "flex-basis 200ms, padding 200ms",
        }}>
          {sidebarCollapsed ? (
            <Tooltip title={`展开历史大纲（${filteredRuns.length}）`} placement="right">
              <button onClick={toggleSidebar} className="ghost"
                style={{
                  width: "100%", padding: "8px 4px", fontSize: 12,
                  display: "flex", flexDirection: "column", alignItems: "center", gap: 6,
                  borderColor: "var(--border)",
                }}>
                <RightOutlined />
                <HistoryOutlined style={{ fontSize: 16, color: "var(--accent-2)" }} />
                <span style={{ fontSize: 11, fontWeight: 600 }}>{filteredRuns.length}</span>
              </button>
            </Tooltip>
          ) : (
            <>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
                <h2 style={{ margin: 0, fontSize: 14 }}>历史大纲 · {filteredRuns.length}</h2>
                <Tooltip title="折叠侧栏，让图谱占满" placement="left">
                  <button onClick={toggleSidebar} className="ghost"
                    style={{ padding: "2px 8px", fontSize: 11 }}>
                    <LeftOutlined />
                  </button>
                </Tooltip>
              </div>
              {arcId === "" && (
                <p className="muted" style={{ fontSize: 13 }}>请选择 arc 以查看对应历史大纲</p>
              )}
              {arcId !== "" && filteredRuns.length === 0 && (
                <p className="muted">该 arc 还没有历史大纲</p>
              )}
              <div style={{ display: "grid", gap: 6 }}>
                {filteredRuns.map((r) => (
                  <button key={r.id} onClick={async () => {
                      const d = await api.outlineGet(r.id);
                      setSelected(d);
                    }}
                    className="ghost"
                    style={{
                      textAlign: "left", padding: 10,
                      borderColor: selected?.id === r.id ? "var(--accent-2)" : "var(--border)",
                      background: selected?.id === r.id ? "rgba(187,154,247,.06)" : undefined,
                      fontSize: 12,
                    }}>
                    <div style={{ fontWeight: 600, color: "var(--accent-2)" }}>
                      ✦ {r.phase_name || "(未命名 phase)"}
                    </div>
                    <div className="muted" style={{ marginTop: 4 }}>
                      <span style={{ background: "rgba(187,154,247,.12)", color: "#bb9af7", padding: "1px 6px", borderRadius: 3, fontSize: 11 }}>
                        #{r.id}
                      </span>
                      {" "}
                      <span style={{ fontFamily: "monospace", fontSize: 11 }}>
                        {r.source_kind === "arc" ? "arc" : "predict"}#{r.source_run_id}
                        {" · 候选 "}{r.source_chosen_index ?? 0}
                        {" · phase "}{r.phase_index ?? 0}
                      </span>
                    </div>
                    <div className="muted" style={{ marginTop: 2 }}>
                      第 {r.chapter_start}–{r.chapter_end} 章 · 共 {r.chapter_count} 章
                    </div>
                    <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>
                      ${r.cost_usd?.toFixed(4)} · {r.created_at?.slice(5, 16).replace("T", " ")}
                    </div>
                  </button>
                ))}
              </div>
            </>
          )}
        </div>

        {/* 右：详情 */}
        <div style={{ flex: 1, minWidth: 0 }}>
          {selected ? <OutlineDetail run={selected} draftMap={draftMap} onChange={async () => {
              const d = await api.outlineGet(selected.id);
              setSelected(d);
              reloadDrafts();
            }} /> : (
            <div className="card muted" style={{ minHeight: 200, display: "flex", alignItems: "center", justifyContent: "center" }}>
              {sidebarCollapsed ? "展开侧栏选择历史大纲" : "从左边选一个大纲查看详情"}
            </div>
          )}
        </div>
      </div>
    </>
  );
}

function OutlineDetail({ run, draftMap, onChange }: {
  run: any; draftMap: Map<string, any>; onChange: () => void;
}) {
  const { theme } = useTheme();
  const sourceHref =
    run.source_kind === "arc"
      ? `/arc?id=${run.source_run_id}&candidate=${run.source_chosen_index ?? 0}`
      : `/predict?id=${run.source_run_id}`;
  return (
    <div className="card" style={{ marginBottom: 0 }}>
      {/* breadcrumb back to source */}
      <div style={{ marginBottom: 8 }}>
        <Link href={sourceHref} style={{
          fontSize: 12,
          color: "var(--muted)",
          textDecoration: "none",
          display: "inline-flex",
          alignItems: "center",
          gap: 4,
        }}>
          ← 来自 {run.source_kind === "arc" ? "全弧" : "预测"} #{run.source_run_id}
          {" · 候选 "}{run.source_chosen_index ?? 0}
          {run.phase_name ? ` · ${run.phase_name}` : ""}
        </Link>
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 8 }}>
        <h2 style={{ margin: 0 }}>
          #{run.id} · {run.phase_name}
          <span className="muted" style={{ fontSize: 12, marginLeft: 8 }}>
            ch {run.chapter_start}-{run.chapter_end} · {run.chapters?.length || 0} 章
          </span>
        </h2>
        <span className="muted" style={{ fontSize: 12 }}>${run.cost_usd?.toFixed(4)}</span>
      </div>
      {run.user_hints && (
        <p className="muted" style={{ fontSize: 12, padding: "6px 10px", background: "var(--panel-2)", borderRadius: 4, borderLeft: "3px solid var(--accent-2)" }}>
          偏好：{run.user_hints}
        </p>
      )}
      {theme === "modern" ? (
        <div style={{ marginTop: 12 }}>
          <ChapterFlowGraph runId={run.id} chapters={run.chapters || []} height="calc(100vh - 280px)" />
          <p className="muted" style={{ fontSize: 11, marginTop: 6 }}>
            点击节点查看完整大纲。需要编辑章节字段，请切换到 classic 风格。
          </p>
        </div>
      ) : (
        <div style={{ display: "grid", gap: 10, marginTop: 10 }}>
          {(run.chapters || []).map((c: any) => (
            <ChapterCard key={c.chapter_index} runId={run.id} chapter={c}
              existingDraft={draftMap.get(`${run.id}|${c.chapter_index}`)}
              onChange={onChange} />
          ))}
        </div>
      )}
    </div>
  );
}

function ChapterCard({ runId, chapter, existingDraft, onChange }: {
  runId: number;
  chapter: any;
  existingDraft?: any;
  onChange: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<any>(chapter);
  const [writing, setWriting] = useState(false);
  const [writeMsg, setWriteMsg] = useState("");
  const [progress, setProgress] = useState<{ attempt: number; stage: string; reviewers_done: number } | null>(null);

  const save = async () => {
    const patch: any = {};
    for (const k of ["title", "intent", "must_include", "must_avoid", "key_events",
                      "pacing", "word_target", "ending_hook"]) {
      if (draft[k] !== chapter[k]) patch[k] = draft[k];
    }
    if (Object.keys(patch).length > 0) {
      await api.outlinePatchChapter(runId, chapter.chapter_index, patch);
      onChange();
    }
    setEditing(false);
  };

  const triggerWrite = async () => {
    setWriting(true);
    setWriteMsg("");
    setProgress({ attempt: 1, stage: "starting", reviewers_done: 0 });

    const poll = async () => {
      try {
        const list = await api.draftList();
        const row = list.find((d: any) => d.outline_run_id === runId && d.chapter_index === chapter.chapter_index);
        if (!row) return;
        const d = await api.draftGet(row.id);
        const last = (d.attempts || []).slice(-1)[0];
        if (last) {
          setProgress({
            attempt: last.attempt,
            stage: last.stage || (d.status || "writing"),
            reviewers_done: Object.keys(last.reviews || {}).length,
          });
        }
      } catch {}
    };
    const timer = setInterval(poll, 1500);
    poll();

    try {
      const r = await api.draftWrite(runId, chapter.chapter_index, { skip_reviews: false, max_attempts: 3 });
      setWriteMsg(`✅ ${r.status} · ${r.attempts.length} 轮 · $${r.cost_usd.toFixed(4)}`);
      onChange();
    } catch (e: any) {
      setWriteMsg("失败：" + String(e));
    } finally {
      clearInterval(timer);
      setWriting(false);
      setProgress(null);
    }
  };

  const stageLabel = (s: string) => ({
    starting: "准备中…",
    writer: "Writer 写稿中…",
    writer_done: "Writer 完稿，开始评审",
    reviewing: "三审并行",
    editor: "Editor 仲裁中",
    done: "本轮完成",
  } as Record<string, string>)[s] || s;

  return (
    <div style={{ background: "var(--panel-2)", borderRadius: 6, padding: 12, borderLeft: "3px solid var(--accent)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap", gap: 8 }}>
        <strong style={{ fontSize: 14 }}>
          第 {chapter.chapter_index} 章 · {chapter.title}
          {existingDraft && (
            <span className="tag" style={{
              marginLeft: 8, fontSize: 10,
              background: "rgba(126,207,106,.15)", color: "var(--good)",
            }}>
              ✓ 已写 #{existingDraft.id}
            </span>
          )}
        </strong>
        <div style={{ display: "flex", gap: 6 }}>
          {!editing && (
            <button onClick={() => { setDraft(chapter); setEditing(true); }} className="ghost"
              style={{ padding: "4px 10px", fontSize: 12 }}>编辑</button>
          )}
          {editing && (
            <>
              <button onClick={save} style={{ padding: "4px 10px", fontSize: 12 }}>保存</button>
              <button onClick={() => setEditing(false)} className="ghost"
                style={{ padding: "4px 10px", fontSize: 12 }}>取消</button>
            </>
          )}
          {existingDraft ? (
            <Link href={`/draft?id=${existingDraft.id}`}
              style={{
                padding: "4px 10px", fontSize: 12, textDecoration: "none",
                background: "rgba(126,207,106,.15)", color: "var(--good)",
                border: "1px solid var(--good)",
                borderRadius: 6, fontWeight: 600,
              }}>
              查看成稿 →
            </Link>
          ) : (
            <button onClick={triggerWrite} disabled={writing}
              style={{
                padding: "4px 10px", fontSize: 12,
                background: "var(--accent-2)", color: "#0e1015",
                borderRadius: 6, fontWeight: 600,
              }}>
              {writing ? "写作中…" : "续写 →"}
            </button>
          )}
        </div>
      </div>
      {writing && progress && (
        <div style={{
          marginTop: 8, fontSize: 11, padding: "6px 10px",
          background: "rgba(122,162,247,.08)", borderRadius: 4,
          border: "1px solid rgba(122,162,247,.2)",
          color: "var(--accent)",
        }}>
          <span style={{ fontWeight: 600 }}>第 {progress.attempt} 轮</span>
          {" · "}
          <span>{stageLabel(progress.stage)}</span>
          {progress.stage === "reviewing" && (
            <span style={{ marginLeft: 6, color: "var(--muted)" }}>
              ({progress.reviewers_done}/3 审查完成)
            </span>
          )}
        </div>
      )}
      {writeMsg && (
        <p style={{ fontSize: 11, marginTop: 6, color: writeMsg.startsWith("✅") ? "var(--good)" : "var(--bad)" }}>
          {writeMsg}
        </p>
      )}
      {editing ? (
        <EditForm draft={draft} setDraft={setDraft} />
      ) : (
        <ReadView c={chapter} />
      )}
    </div>
  );
}

function ReadView({ c }: { c: any }) {
  return (
    <div style={{ marginTop: 8, fontSize: 13 }}>
      {c.intent && <p className="muted" style={{ margin: "4px 0" }}><strong style={{ color: "var(--text)" }}>意图：</strong>{c.intent}</p>}
      {(c.must_include || []).length > 0 && (
        <div style={{ marginTop: 6 }}>
          <strong style={{ fontSize: 12, color: "var(--good)" }}>must include:</strong>
          <ul style={{ margin: "2px 0 0 18px", padding: 0 }}>
            {c.must_include.map((x: string, i: number) => <li key={i}>{x}</li>)}
          </ul>
        </div>
      )}
      {(c.must_avoid || []).length > 0 && (
        <div style={{ marginTop: 6 }}>
          <strong style={{ fontSize: 12, color: "var(--bad)" }}>must avoid:</strong>
          <ul style={{ margin: "2px 0 0 18px", padding: 0 }}>
            {c.must_avoid.map((x: string, i: number) => <li key={i}>{x}</li>)}
          </ul>
        </div>
      )}
      {(c.key_events || []).length > 0 && (
        <div style={{ marginTop: 6 }}>
          <strong style={{ fontSize: 12 }}>关键事件:</strong>
          <ol style={{ margin: "2px 0 0 18px", padding: 0 }}>
            {c.key_events.map((x: string, i: number) => <li key={i}>{x}</li>)}
          </ol>
        </div>
      )}
      <div style={{ display: "flex", gap: 6, marginTop: 8, flexWrap: "wrap" }}>
        {c.pacing && <span className="tag" style={{ background: "rgba(122,162,247,.15)", color: "#7aa2f7" }}>节奏: {c.pacing}</span>}
        {c.word_target && <span className="tag">~{c.word_target} 字</span>}
        {(c.foreshadow_ids_addressed || []).length > 0 && (
          <span className="tag" style={{ background: "rgba(187,154,247,.15)", color: "#bb9af7" }}>
            收束伏笔 #{c.foreshadow_ids_addressed.join(", #")}
          </span>
        )}
        {(c.involved_entities || []).length > 0 && (
          <span className="tag" style={{ background: "rgba(126,207,106,.15)", color: "#9ece6a" }}>
            人物: {c.involved_entities.join("、")}
          </span>
        )}
      </div>
      {c.ending_hook && (
        <p className="muted" style={{ marginTop: 6, fontSize: 12, fontStyle: "italic" }}>
          钩子：{c.ending_hook}
        </p>
      )}
    </div>
  );
}

function EditForm({ draft, setDraft }: { draft: any; setDraft: (d: any) => void }) {
  const fld = (k: string, v: any) => setDraft({ ...draft, [k]: v });
  const arrFld = (k: string, v: string) =>
    setDraft({ ...draft, [k]: v.split("\n").map((s) => s.trim()).filter(Boolean) });

  const inputStyle = {
    width: "100%", background: "var(--bg)", color: "var(--text)",
    border: "1px solid var(--border)", borderRadius: 4, padding: 6,
    fontFamily: "inherit", fontSize: 13, marginTop: 2,
  } as const;

  return (
    <div style={{ marginTop: 8, display: "grid", gap: 8 }}>
      <label style={{ fontSize: 12 }}>title<input value={draft.title || ""} onChange={(e) => fld("title", e.target.value)} style={inputStyle} /></label>
      <label style={{ fontSize: 12 }}>intent<input value={draft.intent || ""} onChange={(e) => fld("intent", e.target.value)} style={inputStyle} /></label>
      <label style={{ fontSize: 12 }}>must_include（每行一条）<textarea rows={3} value={(draft.must_include || []).join("\n")} onChange={(e) => arrFld("must_include", e.target.value)} style={inputStyle} /></label>
      <label style={{ fontSize: 12 }}>must_avoid（每行一条）<textarea rows={2} value={(draft.must_avoid || []).join("\n")} onChange={(e) => arrFld("must_avoid", e.target.value)} style={inputStyle} /></label>
      <label style={{ fontSize: 12 }}>key_events（每行一条）<textarea rows={4} value={(draft.key_events || []).join("\n")} onChange={(e) => arrFld("key_events", e.target.value)} style={inputStyle} /></label>
      <label style={{ fontSize: 12 }}>pacing<input value={draft.pacing || ""} onChange={(e) => fld("pacing", e.target.value)} style={inputStyle} /></label>
      <label style={{ fontSize: 12 }}>word_target<input type="number" value={draft.word_target || 3000} onChange={(e) => fld("word_target", +e.target.value)} style={{...inputStyle, width: 120}} /></label>
      <label style={{ fontSize: 12 }}>ending_hook<input value={draft.ending_hook || ""} onChange={(e) => fld("ending_hook", e.target.value)} style={inputStyle} /></label>
    </div>
  );
}
