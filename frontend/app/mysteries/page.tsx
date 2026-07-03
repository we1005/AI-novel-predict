"use client";

import { useEffect, useMemo, useState } from "react";
import { Drawer, Tag } from "antd";
import { api } from "@/lib/api";
import { useTheme } from "@/components/ThemeProvider";
import PageTitle from "@/components/PageTitle";
import BranchViewPicker from "@/components/BranchViewPicker";

const CATEGORY_LABEL: Record<string, string> = {
  identity: "身份谜团",
  dynasty: "王朝兴衰",
  worldview: "世界本源",
  mastermind: "幕后操盘",
  motive: "动机真相",
  prophecy: "预言命运",
  relationship: "关系真相",
  history: "历史真相",
};

const CATEGORY_COLOR: Record<string, string> = {
  identity: "#bb9af7",
  dynasty: "#f7768e",
  worldview: "#7aa2f7",
  mastermind: "#e0af68",
  motive: "#9ece6a",
  prophecy: "#7dcfff",
  relationship: "#73daca",
  history: "#ff9e64",
};

const SEVERITY_LABEL: Record<string, string> = { core: "核心", major: "重要", minor: "次要" };
const STATUS_LABEL: Record<string, string> = {
  open: "开放",
  sharpened: "强化",
  partially_resolved: "部分回应",
  resolved: "已收束",
  contradicted: "矛盾",
};
const STATUS_COLOR: Record<string, string> = {
  open: "#7aa2f7",
  sharpened: "#bb9af7",
  partially_resolved: "#e0af68",
  resolved: "#9ece6a",
  contradicted: "#f7768e",
};

const CHANGE_LABEL: Record<string, string> = {
  first_seen: "首次浮现",
  sharpened: "新线索强化",
  resolved: "明确收束",
  contradicted: "证据矛盾",
};

export default function MysteriesPage() {
  const { theme } = useTheme();
  const [items, setItems] = useState<any[]>([]);
  const [entityById, setEntityById] = useState<Record<number, any>>({});
  const [drawerMystery, setDrawerMystery] = useState<any | null>(null);
  const [busy, setBusy] = useState(false);
  const [busySince, setBusySince] = useState<number | null>(null);
  const [, setTick] = useState(0);
  const [msg, setMsg] = useState("");
  const [filterCat, setFilterCat] = useState<string>("all");
  const [filterSev, setFilterSev] = useState<string>("all");
  const [filterStatus, setFilterStatus] = useState<string>("active");
  const [showLowConf, setShowLowConf] = useState(false);
  const [book, setBook] = useState("");   // 视角:""=原文,否则分支 slug

  const load = () => api.mysteries(book || undefined).then(setItems).catch((e) => setMsg(String(e)));

  useEffect(() => {
    load();
    api.entities({}).then((es) => {
      const byId: Record<number, any> = {};
      for (const e of es) byId[e.id] = e;
      setEntityById(byId);
    }).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [book]);

  useEffect(() => {
    if (!busy) return;
    const t = setInterval(() => setTick((x) => x + 1), 1000);
    return () => clearInterval(t);
  }, [busy]);

  const rebuild = async (skipExisting: boolean) => {
    setBusy(true);
    setBusySince(Date.now());
    setMsg("");
    try {
      const r = await api.mysteriesRebuild(skipExisting);
      await load();
      setMsg(`✅ 处理 ${r.batches_processed}/${r.batches_processed + r.batches_failed} 批 · 现有 ${r.mysteries_total} 条疑点 · 花费 $${r.cost_usd.toFixed(4)} · 耗时 ${r.elapsed_s}s`);
    } catch (e: any) {
      setMsg(String(e));
    } finally {
      setBusy(false);
      setBusySince(null);
    }
  };

  const remove = async (id: number) => {
    if (!confirm("确定删除？")) return;
    await api.mysteryDelete(id);
    load();
  };

  const elapsed = busy && busySince ? Math.floor((Date.now() - busySince) / 1000) : 0;

  const stats = useMemo(() => {
    const byCat: Record<string, number> = {};
    const bySev: Record<string, number> = {};
    const byStatus: Record<string, number> = {};
    for (const it of items) {
      byCat[it.category] = (byCat[it.category] || 0) + 1;
      bySev[it.severity] = (bySev[it.severity] || 0) + 1;
      byStatus[it.status || "open"] = (byStatus[it.status || "open"] || 0) + 1;
    }
    return { byCat, bySev, byStatus };
  }, [items]);

  const filtered = useMemo(() => {
    return items.filter((it: any) => {
      const status = it.status || "open";
      if (filterStatus === "active" && (status === "resolved" || status === "contradicted")) return false;
      if (filterStatus !== "all" && filterStatus !== "active" && status !== filterStatus) return false;
      if (filterCat !== "all" && it.category !== filterCat) return false;
      if (filterSev !== "all" && it.severity !== filterSev) return false;
      const conf = it.confidence ?? 50;
      if (!showLowConf && conf < 50) return false;
      return true;
    });
  }, [items, filterCat, filterSev, filterStatus, showLowConf]);

  return (
    <>
      <PageTitle title="宏观疑点"
        subtitle="读完整本书还在追问的大问题：身份 · 王朝 · 世界本源 · 幕后。每条带浮现/强化/收束时间线" />

      <BranchViewPicker value={book} onChange={setBook} style={{ marginBottom: 12 }} />

      <div className="card">
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
          <div>
            <button onClick={() => rebuild(false)} disabled={busy}>
              {busy ? `分析中… ${elapsed}s` : "🔄 全量重建（清空 auto 后按批次回放）"}
            </button>
            <button onClick={() => rebuild(true)} disabled={busy} className="ghost" style={{ marginLeft: 6 }}>
              ⏩ 增量补跑（跳过已处理批次）
            </button>
            <p className="muted" style={{ fontSize: 12, marginTop: 6, marginBottom: 0 }}>
              全量重建按章节顺序对每批跑一次 MysteryAgent，会建立完整的浮现/强化时间线。约 5-10 分钟，~$0.10。
            </p>
          </div>
          {items.length > 0 && (
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <Stat k="总数" v={items.length} />
              <Stat k="核心" v={stats.bySev.core || 0} color="var(--bad)" />
              <Stat k="重要" v={stats.bySev.major || 0} color="var(--warn)" />
              <Stat k="已收束" v={stats.byStatus.resolved || 0} color="var(--good)" />
            </div>
          )}
        </div>
        {msg && (
          <p style={{ marginTop: 8, fontSize: 12, color: msg.startsWith("✅") ? "var(--good)" : "var(--bad)" }}>{msg}</p>
        )}
      </div>

      {items.length > 0 && (
        <div className="card">
          <div className="row" style={{ alignItems: "center", flexWrap: "wrap" }}>
            <span className="muted">状态</span>
            {(["active", "all", "open", "sharpened", "partially_resolved", "resolved", "contradicted"] as const).map((s) => (
              <button key={s} onClick={() => setFilterStatus(s)}
                className={filterStatus === s ? "" : "ghost"}
                style={{ padding: "4px 10px", fontSize: 12, borderColor: STATUS_COLOR[s] || "var(--border)" }}>
                {s === "active" ? "进行中" : s === "all" ? "全部" : STATUS_LABEL[s]}
              </button>
            ))}
            <span className="muted" style={{ marginLeft: 14 }}>分类</span>
            <button onClick={() => setFilterCat("all")} className={filterCat === "all" ? "" : "ghost"}
              style={{ padding: "4px 10px", fontSize: 12 }}>全部</button>
            {Object.keys(stats.byCat).map((c) => (
              <button key={c} onClick={() => setFilterCat(c)}
                className={filterCat === c ? "" : "ghost"}
                style={{ padding: "4px 10px", fontSize: 12, borderColor: CATEGORY_COLOR[c] || "var(--border)" }}>
                <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: 2, background: CATEGORY_COLOR[c] || "#888", marginRight: 4 }} />
                {CATEGORY_LABEL[c] || c} {stats.byCat[c]}
              </button>
            ))}
            <span className="muted" style={{ marginLeft: 14 }}>严重度</span>
            {(["all", "core", "major", "minor"] as const).map((s) => (
              <button key={s} onClick={() => setFilterSev(s)}
                className={filterSev === s ? "" : "ghost"}
                style={{ padding: "4px 10px", fontSize: 12 }}>
                {s === "all" ? "全部" : SEVERITY_LABEL[s]}
              </button>
            ))}
            <label style={{ marginLeft: 14, fontSize: 12, color: "var(--muted)", display: "flex", alignItems: "center", gap: 4 }}>
              <input type="checkbox" checked={showLowConf} onChange={(e) => setShowLowConf(e.target.checked)} />
              显示低置信 (&lt;50)
            </label>
          </div>
        </div>
      )}

      <div style={{
        display: theme === "modern" ? "grid" : "grid",
        gap: 12,
        gridTemplateColumns: theme === "modern" ? "repeat(auto-fill, minmax(320px, 1fr))" : "1fr",
      }}>
        {filtered.map((m: any) => (
          theme === "modern" ? (
            <MysteryCardCompact
              key={m.id}
              mystery={m}
              onClick={() => setDrawerMystery(m)}
              onRemove={() => remove(m.id)}
            />
          ) : (
            <MysteryCard key={m.id} mystery={m} entityById={entityById} onRemove={() => remove(m.id)} onLoad={load} />
          )
        ))}
        {items.length === 0 && !busy && (
          <div className="card muted">
            还没有疑点。点击上方 <strong>🔄 全量重建</strong> 让 MysteryAgent 按批次扫描全书一次。
          </div>
        )}
        {items.length > 0 && filtered.length === 0 && (
          <div className="card muted">当前筛选下没有条目</div>
        )}
      </div>

      {/* Modern theme: detail Drawer */}
      <Drawer
        title={drawerMystery ? `[${CATEGORY_LABEL[drawerMystery.category] || drawerMystery.category}] ${drawerMystery.question.slice(0, 30)}…` : ""}
        placement="right"
        width={560}
        open={!!drawerMystery}
        onClose={() => setDrawerMystery(null)}
        mask={false}
      >
        {drawerMystery && (
          <MysteryDetailContent mystery={drawerMystery} entityById={entityById}
            onRemove={async () => { await remove(drawerMystery.id); setDrawerMystery(null); }}
            onLoad={async () => { await load(); }} />
        )}
      </Drawer>
    </>
  );
}

// Compact card for modern grid view — minimal preview, click opens drawer.
function MysteryCardCompact({ mystery, onClick, onRemove }: {
  mystery: any; onClick: () => void; onRemove: () => void;
}) {
  const catColor = CATEGORY_COLOR[mystery.category] || "#888";
  const status = mystery.status || "open";
  const statusColor = STATUS_COLOR[status] || "#888";
  const confidence = mystery.confidence ?? 50;

  return (
    <div onClick={onClick} className="card" style={{
      marginBottom: 0,
      borderLeft: `3px solid ${catColor}`,
      cursor: "pointer",
      transition: "transform 120ms",
      opacity: status === "resolved" ? 0.7 : 1,
    }}>
      <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap", marginBottom: 6 }}>
        <span className="tag" style={{ background: `${catColor}25`, color: catColor }}>
          {CATEGORY_LABEL[mystery.category] || mystery.category}
        </span>
        <span className="tag" style={{ background: `${statusColor}25`, color: statusColor }}>
          {STATUS_LABEL[status]}
        </span>
        {mystery.severity === "core" && (
          <span className="tag" style={{ background: "rgba(247,118,142,.2)", color: "var(--bad)" }}>核心</span>
        )}
      </div>
      <div className="prose-cn" style={{
        fontSize: 14, lineHeight: 1.5, fontWeight: 500,
        display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: "vertical", overflow: "hidden",
      }}>
        {mystery.question}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 10 }}>
        <div style={{ flex: 1, height: 4, background: "var(--panel-2)", borderRadius: 2 }}>
          <div style={{
            width: `${confidence}%`, height: "100%",
            background: confidence >= 80 ? "var(--good)" : confidence >= 50 ? "var(--accent)" : "var(--warn)",
            borderRadius: 2,
          }} />
        </div>
        <span className="muted" style={{ fontSize: 11 }}>{confidence}</span>
        <span className="muted" style={{ fontSize: 11 }}>{(mystery.updates_log || []).length} log</span>
      </div>
    </div>
  );
}

// Drawer body: identical structure to classic MysteryCard but flowing top-to-bottom.
function MysteryDetailContent({ mystery, entityById, onRemove, onLoad }: {
  mystery: any; entityById: Record<number, any>; onRemove: () => void; onLoad: () => void;
}) {
  const [editingNote, setEditingNote] = useState(false);
  const [noteDraft, setNoteDraft] = useState(mystery.note || "");
  const status = mystery.status || "open";
  const confidence = mystery.confidence ?? 50;
  const catColor = CATEGORY_COLOR[mystery.category] || "#888";
  const statusColor = STATUS_COLOR[status] || "#888";

  const saveNote = async () => {
    await api.mysteryNote(mystery.id, noteDraft);
    setEditingNote(false);
    onLoad();
  };

  const entities = (mystery.related_entity_ids || [])
    .map((id: number) => entityById[id])
    .filter(Boolean);
  const log = mystery.updates_log || [];

  return (
    <div className="prose-cn" style={{ color: "var(--text)" }}>
      <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 12, flexWrap: "wrap" }}>
        <Tag color={catColor}>{CATEGORY_LABEL[mystery.category] || mystery.category}</Tag>
        <Tag color={statusColor}>{STATUS_LABEL[status]}</Tag>
        <Tag>{SEVERITY_LABEL[mystery.severity] || mystery.severity}</Tag>
        {mystery.source !== "auto" && <Tag>手动</Tag>}
      </div>

      <h2 style={{ fontSize: 17, lineHeight: 1.55, margin: "0 0 12px", color: "var(--text)" }}>
        {mystery.question}
      </h2>

      {mystery.why_it_matters && (
        <div style={{
          background: "var(--panel-2)", padding: 10, borderRadius: 4, marginBottom: 12,
          borderLeft: "3px solid var(--c-story)",
        }}>
          <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 4, fontWeight: 600 }}>为什么重要</div>
          <p style={{ margin: 0, fontSize: 13, lineHeight: 1.6 }}>{mystery.why_it_matters}</p>
        </div>
      )}

      {/* confidence bar */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
        <span className="muted" style={{ fontSize: 11, minWidth: 60 }}>置信度</span>
        <div style={{ flex: 1, height: 6, background: "var(--panel-2)", borderRadius: 3 }}>
          <div style={{
            width: `${confidence}%`, height: "100%",
            background: confidence >= 80 ? "var(--good)" : confidence >= 50 ? "var(--accent)" : "var(--warn)",
            borderRadius: 3,
          }} />
        </div>
        <span className="muted" style={{ fontSize: 11, minWidth: 30, textAlign: "right" }}>{confidence}</span>
      </div>

      {(mystery.clues || []).length > 0 && (
        <div style={{ background: "var(--panel-2)", padding: 10, borderRadius: 4, marginBottom: 12,
                       borderLeft: "3px solid var(--c-foreshadow)" }}>
          <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 4, fontWeight: 600 }}>
            书中线索（{mystery.clues.length}）
          </div>
          <ol style={{ margin: 0, paddingLeft: 18, fontSize: 13, lineHeight: 1.65 }}>
            {(mystery.clues || []).slice(-8).map((c: string, i: number) => <li key={i}>{c}</li>)}
            {mystery.clues.length > 8 && (
              <li className="muted" style={{ fontStyle: "italic" }}>…前面还有 {mystery.clues.length - 8} 条</li>
            )}
          </ol>
        </div>
      )}

      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 12 }}>
        {entities.length > 0 && (
          <Tag color="green">涉及人物：{entities.map((e: any) => e.name).join("、")}</Tag>
        )}
        {(mystery.related_foreshadow_ids || []).length > 0 && (
          <Tag color="purple">关联伏笔 #{mystery.related_foreshadow_ids.join(", #")}</Tag>
        )}
      </div>

      {/* timeline */}
      {log.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 6, fontWeight: 600 }}>演变时间线</div>
          <div style={{ position: "relative", paddingLeft: 12 }}>
            <div style={{ position: "absolute", left: 4, top: 6, bottom: 6, width: 2, background: "var(--border)" }} />
            {log.map((entry: any, i: number) => {
              const change = entry.change || "first_seen";
              const dotColor = change === "first_seen" ? "#7aa2f7"
                : change === "sharpened" ? "#bb9af7"
                : change === "resolved" ? "#9ece6a"
                : "#f7768e";
              return (
                <div key={i} style={{ position: "relative", padding: "6px 0 6px 16px" }}>
                  <div style={{
                    position: "absolute", left: -2, top: 10, width: 10, height: 10,
                    borderRadius: "50%", background: dotColor,
                    boxShadow: `0 0 0 2px var(--panel)`,
                  }} />
                  <div style={{ fontSize: 12, color: "var(--muted)" }}>
                    <span style={{ color: dotColor, fontWeight: 600 }}>{CHANGE_LABEL[change] || change}</span>
                    {" · "}
                    {entry.chapter_range ? `第 ${entry.chapter_range[0]}–${entry.chapter_range[1]} 章` : "—"}
                    {entry.batch_id != null && ` · 批 #${entry.batch_id}`}
                  </div>
                  <div style={{ fontSize: 13, marginTop: 2 }}>{entry.summary}</div>
                  {entry.new_clue && (
                    <div className="muted" style={{ fontSize: 12, marginTop: 2, fontStyle: "italic" }}>
                      新线索: {entry.new_clue}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* user note */}
      <div style={{ padding: 10, background: "var(--panel-2)", borderRadius: 4,
                     borderLeft: "2px solid var(--accent-2)", marginBottom: 12 }}>
        <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 4, fontWeight: 600 }}>我的猜想 / 笔记</div>
        {editingNote ? (
          <>
            <textarea value={noteDraft} onChange={(e) => setNoteDraft(e.target.value)} rows={3}
              style={{ width: "100%", background: "var(--bg)", color: "var(--text)",
                       border: "1px solid var(--border)", borderRadius: 4, padding: 6,
                       fontFamily: "inherit", fontSize: 13 }} />
            <div style={{ marginTop: 6 }}>
              <button onClick={saveNote} style={{ padding: "4px 10px", fontSize: 12 }}>保存</button>
              <button onClick={() => { setEditingNote(false); setNoteDraft(mystery.note || ""); }}
                className="ghost" style={{ padding: "4px 10px", fontSize: 12, marginLeft: 6 }}>取消</button>
            </div>
          </>
        ) : (
          <div onClick={() => setEditingNote(true)} style={{ cursor: "text", fontSize: 13, minHeight: 18,
                  color: mystery.note ? "var(--text)" : "var(--muted)" }}>
            {mystery.note || "（点击添加）"}
          </div>
        )}
      </div>

      <div style={{ display: "flex", justifyContent: "flex-end" }}>
        <button onClick={onRemove} className="ghost" style={{ padding: "6px 14px", fontSize: 12 }}>
          删除该疑点
        </button>
      </div>
    </div>
  );
}

function Stat({ k, v, color }: { k: string; v: number | string; color?: string }) {
  return (
    <div className="metric" style={{ minWidth: 80, padding: "8px 12px" }}>
      <div className="k" style={color ? { color } : undefined}>{k}</div>
      <div className="v" style={{ fontSize: 18 }}>{v}</div>
    </div>
  );
}

function MysteryCard({ mystery, entityById, onRemove, onLoad }: {
  mystery: any; entityById: Record<number, any>; onRemove: () => void; onLoad: () => void;
}) {
  const [editingNote, setEditingNote] = useState(false);
  const [noteDraft, setNoteDraft] = useState(mystery.note || "");
  const [showLog, setShowLog] = useState(false);

  const saveNote = async () => {
    await api.mysteryNote(mystery.id, noteDraft);
    setEditingNote(false);
    onLoad();
  };

  const catColor = CATEGORY_COLOR[mystery.category] || "#888";
  const sevColor =
    mystery.severity === "core" ? "var(--bad)" :
    mystery.severity === "major" ? "var(--warn)" : "var(--muted)";
  const status = mystery.status || "open";
  const statusColor = STATUS_COLOR[status] || "#888";
  const confidence = mystery.confidence ?? 50;

  const entities = (mystery.related_entity_ids || [])
    .map((id: number) => entityById[id])
    .filter(Boolean);
  const log = mystery.updates_log || [];

  return (
    <div className="card" style={{
      marginBottom: 0,
      borderLeft: `4px solid ${catColor}`,
      opacity: status === "resolved" ? 0.7 : 1,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 8 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", gap: 6, alignItems: "center", marginBottom: 6, flexWrap: "wrap" }}>
            <span className="tag" style={{ background: `${catColor}25`, color: catColor }}>
              {CATEGORY_LABEL[mystery.category] || mystery.category}
            </span>
            <span className="tag" style={{ background: sevColor === "var(--bad)" ? "rgba(247,118,142,.2)" : sevColor === "var(--warn)" ? "rgba(224,175,104,.2)" : "var(--panel-2)", color: sevColor }}>
              {SEVERITY_LABEL[mystery.severity] || mystery.severity}
            </span>
            <span className="tag" style={{ background: `${statusColor}25`, color: statusColor }}>
              {STATUS_LABEL[status]}
            </span>
            {mystery.source !== "auto" && <span className="tag">手动</span>}
          </div>
          <h3 style={{ margin: "0 0 6px", fontSize: 16, lineHeight: 1.45 }}>{mystery.question}</h3>
          {mystery.why_it_matters && (
            <p className="muted" style={{ margin: "0 0 8px", fontSize: 12, lineHeight: 1.55 }}>
              <strong style={{ color: "var(--text)" }}>为什么重要：</strong>{mystery.why_it_matters}
            </p>
          )}
        </div>
        <button onClick={onRemove} className="ghost" style={{ padding: "4px 10px", fontSize: 12 }}>删除</button>
      </div>

      {/* confidence bar */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 4 }}>
        <span className="muted" style={{ fontSize: 11, minWidth: 60 }}>置信度</span>
        <div style={{ flex: 1, height: 6, background: "var(--panel-2)", borderRadius: 3, overflow: "hidden" }}>
          <div style={{
            width: `${confidence}%`,
            height: "100%",
            background: confidence >= 80 ? "var(--good)" : confidence >= 50 ? "var(--accent)" : "var(--warn)",
            transition: "width 200ms",
          }} />
        </div>
        <span className="muted" style={{ fontSize: 11, minWidth: 30, textAlign: "right" }}>{confidence}</span>
      </div>

      {(mystery.clues || []).length > 0 && (
        <div style={{ background: "var(--panel-2)", padding: 10, borderRadius: 4, marginTop: 8 }}>
          <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 4, fontWeight: 600 }}>
            书中线索（{mystery.clues.length}）
          </div>
          <ol style={{ margin: 0, paddingLeft: 18, fontSize: 13, lineHeight: 1.65 }}>
            {(mystery.clues || []).slice(-5).map((c: string, i: number) => <li key={i}>{c}</li>)}
            {mystery.clues.length > 5 && (
              <li className="muted" style={{ fontStyle: "italic" }}>…前面还有 {mystery.clues.length - 5} 条</li>
            )}
          </ol>
        </div>
      )}

      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 8 }}>
        {entities.length > 0 && (
          <span className="tag" style={{ background: "rgba(126,207,106,.15)", color: "#9ece6a" }}>
            涉及人物：{entities.map((e: any) => e.name).join("、")}
          </span>
        )}
        {(mystery.related_foreshadow_ids || []).length > 0 && (
          <span className="tag" style={{ background: "rgba(187,154,247,.15)", color: "#bb9af7" }}>
            关联伏笔 #{mystery.related_foreshadow_ids.join(", #")}
          </span>
        )}
      </div>

      {/* updates timeline */}
      {log.length > 0 && (
        <div style={{ marginTop: 10 }}>
          <button onClick={() => setShowLog(!showLog)} className="ghost"
            style={{ padding: "4px 10px", fontSize: 12 }}>
            {showLog ? "收起" : "展开"}时间线（{log.length} 条）
          </button>
          {showLog && (
            <div style={{ marginTop: 8, position: "relative", paddingLeft: 12 }}>
              <div style={{ position: "absolute", left: 4, top: 6, bottom: 6, width: 2, background: "var(--border)" }} />
              {log.map((entry: any, i: number) => {
                const change = entry.change || "first_seen";
                const dotColor = change === "first_seen" ? "#7aa2f7"
                  : change === "sharpened" ? "#bb9af7"
                  : change === "resolved" ? "#9ece6a"
                  : "#f7768e";
                return (
                  <div key={i} style={{ position: "relative", padding: "6px 0 6px 16px" }}>
                    <div style={{
                      position: "absolute", left: -2, top: 10, width: 10, height: 10,
                      borderRadius: "50%", background: dotColor,
                      boxShadow: `0 0 0 2px var(--panel)`,
                    }} />
                    <div style={{ fontSize: 12, color: "var(--muted)" }}>
                      <span style={{ color: dotColor, fontWeight: 600 }}>{CHANGE_LABEL[change] || change}</span>
                      {" · "}
                      {entry.chapter_range ? `第 ${entry.chapter_range[0]}–${entry.chapter_range[1]} 章` : "—"}
                      {entry.batch_id != null && ` · 批 #${entry.batch_id}`}
                    </div>
                    <div style={{ fontSize: 13, marginTop: 2 }}>{entry.summary}</div>
                    {entry.new_clue && (
                      <div className="muted" style={{ fontSize: 12, marginTop: 2, fontStyle: "italic" }}>
                        新线索: {entry.new_clue}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* user note */}
      <div style={{ marginTop: 10, padding: 10, background: "var(--panel-2)", borderRadius: 4, borderLeft: "2px solid var(--accent-2)" }}>
        <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 4, fontWeight: 600 }}>我的猜想 / 笔记</div>
        {editingNote ? (
          <>
            <textarea value={noteDraft} onChange={(e) => setNoteDraft(e.target.value)} rows={3}
              style={{ width: "100%", background: "var(--bg)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: 4, padding: 6, fontFamily: "inherit", fontSize: 13 }} />
            <div style={{ marginTop: 6 }}>
              <button onClick={saveNote} style={{ padding: "4px 10px", fontSize: 12 }}>保存</button>
              <button onClick={() => { setEditingNote(false); setNoteDraft(mystery.note || ""); }} className="ghost" style={{ padding: "4px 10px", fontSize: 12, marginLeft: 6 }}>取消</button>
            </div>
          </>
        ) : (
          <div onClick={() => setEditingNote(true)} style={{ cursor: "text", fontSize: 13, minHeight: 18, color: mystery.note ? "var(--text)" : "var(--muted)" }}>
            {mystery.note || "（点击添加 — 你的假设、还想 LLM 进一步分析的方向 等）"}
          </div>
        )}
      </div>
    </div>
  );
}
