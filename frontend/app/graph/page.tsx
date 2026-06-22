"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import cytoscape from "cytoscape";
import { api } from "@/lib/api";
import PersonFlowGraph from "@/components/PersonFlowGraph";
import { useTheme } from "@/components/ThemeProvider";
import { chartPalette } from "@/lib/colors";
import PageTitle from "@/components/PageTitle";

type Tab = "characters" | "foreshadow" | "hero" | "timeline";

const TYPE_COLORS: Record<string, string> = {
  mystery: "#bb9af7",
  promise: "#7aa2f7",
  prophecy: "#7dcfff",
  item: "#e0af68",
  person: "#9ece6a",
  faction: "#f7768e",
  skill: "#ff9e64",
  location: "#73daca",
};

export default function GraphPage() {
  const [tab, setTab] = useState<Tab>("foreshadow");
  const [upTo, setUpTo] = useState<number | "">("");

  return (
    <>
      <PageTitle title="结构图谱" subtitle="伏笔甘特 · 人物关系 · 主角演变 · 剧情时间线" />
      <div className="card">
        <div className="row" style={{ alignItems: "center" }}>
          <button className={tab === "foreshadow" ? "" : "ghost"} onClick={() => setTab("foreshadow")}>
            伏笔甘特图
          </button>
          <button className={tab === "characters" ? "" : "ghost"} onClick={() => setTab("characters")}>
            人物关系
          </button>
          <button className={tab === "hero" ? "" : "ghost"} onClick={() => setTab("hero")}>
            主角演变
          </button>
          <button className={tab === "timeline" ? "" : "ghost"} onClick={() => setTab("timeline")}>
            剧情时间线
          </button>
          <span className="muted" style={{ marginLeft: 16 }}>截至章节</span>
          <input
            type="number"
            placeholder="(全部)"
            value={upTo}
            onChange={(e) => setUpTo(e.target.value === "" ? "" : +e.target.value)}
            style={{ width: 110 }}
          />
        </div>
      </div>

      {tab === "foreshadow" && <ForeshadowGantt upTo={upTo === "" ? undefined : upTo} />}
      {tab === "characters" && <CharacterGraph upTo={upTo === "" ? undefined : upTo} />}
      {tab === "hero" && <HeroEvolution />}
      {tab === "timeline" && <Timeline />}
    </>
  );
}

// ---------------------------------------------------------------------------
// 伏笔甘特图: X = 章节, 每条伏笔一行带颜色，open 延伸到末尾。
// ---------------------------------------------------------------------------

function ForeshadowGantt({ upTo }: { upTo?: number }) {
  const { colorScheme } = useTheme();
  const ref = useRef<HTMLDivElement | null>(null);
  const [data, setData] = useState<{ items: any[]; max_chapter: number } | null>(null);
  const [filter, setFilter] = useState<"all" | "open" | "resolved">("all");
  const [typeFilter, setTypeFilter] = useState<string>("all");

  useEffect(() => {
    api.graphForeshadowings(upTo).then((r: any) => setData(r));
  }, [upTo]);

  const filtered = useMemo(() => {
    if (!data) return [];
    return data.items.filter((it: any) => {
      if (filter !== "all" && it.status !== filter) return false;
      if (typeFilter !== "all" && it.type !== typeFilter) return false;
      return true;
    });
  }, [data, filter, typeFilter]);

  useEffect(() => {
    if (!ref.current || !data) return;
    let chart: any;
    const max = data.max_chapter || 1472;

    // Sort by planted_chapter so the chart reads left-to-right by birth order.
    const items = [...filtered].sort((a, b) => a.planted_chapter - b.planted_chapter);

    (async () => {
      const echarts = await import("echarts");
      chart = echarts.init(ref.current!);
      const p = chartPalette();

      const data1 = items.map((it: any, idx: number) => ({
        name: `#${it.id} ${it.type}`,
        value: [
          idx,
          it.planted_chapter,
          it.resolved_chapter ?? max,
          it.status,
          it.type,
          it.description,
          it.resolved_description ?? "",
          it.id,
        ],
        itemStyle: {
          color: TYPE_COLORS[it.type] || p.muted,
          opacity: it.status === "resolved" ? 0.85 : 0.55,
          borderColor: it.status === "open" ? p.text : "transparent",
          borderWidth: it.status === "open" ? 1 : 0,
          borderType: "dashed" as const,
        },
      }));

      const renderItem = (params: any, apiObj: any) => {
        const idx = apiObj.value(0);
        const start = apiObj.coord([apiObj.value(1), idx]);
        const end = apiObj.coord([apiObj.value(2), idx]);
        const height = apiObj.size([0, 1])[1] * 0.55;
        const rect = {
          x: start[0],
          y: start[1] - height / 2,
          width: Math.max(end[0] - start[0], 2),
          height,
        };
        return {
          type: "rect",
          shape: rect,
          style: apiObj.style(),
        };
      };

      chart.setOption({
        backgroundColor: "transparent",
        tooltip: {
          formatter: (params: any) => {
            const v = params.value;
            const status = v[3] === "open" ? "未收束" : "已收束";
            return `
              <b>#${v[7]} ${v[4]}</b> · <span style="color:${v[3] === "open" ? p.warn : p.good}">${status}</span><br/>
              <span style="opacity:.7">第 ${v[1]} 章</span>${v[2] !== max ? ` → 第 ${v[2]} 章` : " → 至今"}<br/>
              <div style="max-width:480px;white-space:normal;margin-top:6px">${v[5]}</div>
              ${v[6] ? `<div style="max-width:480px;white-space:normal;margin-top:6px;color:${p.good}">→ ${v[6]}</div>` : ""}
            `;
          },
          backgroundColor: p.panel,
          borderColor: p.border,
          textStyle: { color: p.text },
        },
        grid: { left: 60, right: 24, top: 24, bottom: 60 },
        xAxis: {
          type: "value",
          min: 1,
          max,
          name: "章节",
          axisLabel: { color: p.muted },
          splitLine: { lineStyle: { color: p.border } },
        },
        yAxis: {
          type: "value",
          inverse: true,
          min: -0.5,
          max: items.length - 0.5,
          axisLabel: { show: false },
          splitLine: { show: false },
          axisTick: { show: false },
        },
        dataZoom: [
          { type: "slider", xAxisIndex: 0, height: 20, bottom: 20, backgroundColor: p.bg },
          { type: "inside", xAxisIndex: 0 },
        ],
        series: [
          {
            type: "custom",
            renderItem,
            encode: { x: [1, 2], y: 0 },
            data: data1,
          },
        ],
      });
    })();
    return () => { chart?.dispose(); };
  }, [filtered, data, colorScheme]);

  if (!data) return <div className="card">加载中…</div>;
  const total = data.items.length;
  const open = data.items.filter((i: any) => i.status === "open").length;
  const types = Array.from(new Set(data.items.map((i: any) => i.type))).sort();

  return (
    <div className="card">
      <h2>伏笔甘特图 — {total} 条 ({open} 未收束)</h2>
      <p className="muted">
        每行一条伏笔。从"埋下"章节到"收束"章节为一条带；未收束的延伸到末尾，描边为虚线。鼠标悬停看详情。
      </p>
      <div className="row" style={{ alignItems: "center", marginBottom: 8 }}>
        <span className="muted">状态</span>
        {(["all", "open", "resolved"] as const).map((s) => (
          <button key={s} className={filter === s ? "" : "ghost"} onClick={() => setFilter(s)} style={{ padding: "4px 10px", fontSize: 12 }}>
            {s === "all" ? "全部" : s === "open" ? "未收束" : "已收束"}
          </button>
        ))}
        <span className="muted" style={{ marginLeft: 12 }}>类型</span>
        <button className={typeFilter === "all" ? "" : "ghost"} onClick={() => setTypeFilter("all")} style={{ padding: "4px 10px", fontSize: 12 }}>
          全部
        </button>
        {types.map((t: string) => (
          <button
            key={t}
            className={typeFilter === t ? "" : "ghost"}
            onClick={() => setTypeFilter(t)}
            style={{ padding: "4px 10px", fontSize: 12, borderColor: TYPE_COLORS[t] || "var(--border)" }}
          >
            <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: 2, background: TYPE_COLORS[t] || "#888", marginRight: 4 }} />
            {t}
          </button>
        ))}
      </div>
      <div ref={ref} style={{ width: "100%", height: Math.min(Math.max(filtered.length * 14 + 80, 320), 900), background: "var(--panel-2)", borderRadius: 8 }} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// 人物关系: cytoscape, importance 决定大小，多源边权重决定线粗细。
// ---------------------------------------------------------------------------

function CharacterGraph({ upTo }: { upTo?: number }) {
  const { theme, colorScheme } = useTheme();
  const ref = useRef<HTMLDivElement | null>(null);
  const [data, setData] = useState<{ nodes: any[]; edges: any[] }>({ nodes: [], edges: [] });
  const [topN, setTopN] = useState(40);
  const [extracting, setExtracting] = useState(false);
  const [msg, setMsg] = useState("");
  const [narrNote, setNarrNote] = useState<string>("");

  // Surface narrative structure (from 文笔风格 analysis) so multi-POV / non-linear
  // books are explained rather than looking "broken".
  useEffect(() => {
    api.styleGet().then((d: any) => {
      const ns = d?.profile?.narrative_structure;
      if (!ns) return;
      const techs: string[] = ns.techniques || [];
      const flags = techs.filter((t) => /多视角|多主角|POV|非线性|插叙|倒叙|环形/i.test(t));
      if (ns.mode === "nonlinear" || flags.length) {
        setNarrNote(`本书叙事：${ns.mode === "nonlinear" ? "非线性" : "线性"}${flags.length ? " · " + flags.join("/") : ""}。多视角/多线的书，同一角色易被分批抽成多个名字——建议先点「整理图谱」去重。`);
      }
    }).catch(() => {});
  }, []);

  const reload = () => {
    api.graphCharacters(upTo || undefined, topN).then(setData).catch(() => {});
  };

  useEffect(() => { reload(); }, [upTo, topN]);

  const labeledEdges = data.edges.filter((e: any) => e.data.kind === "labeled").length;

  const runExtract = async () => {
    setExtracting(true);
    setMsg("");
    try {
      const r = await api.extractRelationships(Math.max(40, topN));
      setMsg(`✅ 角色 ${r.roles_assigned} 个 / 关系 ${r.relationships} 条 · $${r.cost_usd.toFixed(4)}`);
      reload();
    } catch (e: any) {
      setMsg(String(e));
    } finally {
      setExtracting(false);
    }
  };

  // One-click cleanup for messy (multi-batch / multi-POV) books: merge duplicate
  // entities → recompute importance → re-extract relationships.
  const runTidy = async () => {
    setExtracting(true);
    setMsg("");
    try {
      setMsg("① 实体去重中…");
      const d = await api.graphDedup();
      setMsg(`① 去重完成（合并 ${d.merged}）　② 重算重要度…`);
      await api.graphRecomputeImportance();
      setMsg(`① 去重 ${d.merged}　② 重要度已重算　③ 抽取关系中…`);
      const r = await api.extractRelationships(Math.max(40, topN));
      setMsg(`✅ 整理完成：合并 ${d.merged} 个重复实体 · 角色 ${r.roles_assigned} · 关系 ${r.relationships} 条`);
      reload();
    } catch (e: any) {
      setMsg("整理失败：" + String(e));
    } finally {
      setExtracting(false);
    }
  };

  useEffect(() => {
    if (theme === "modern") return; // skip cytoscape init in modern theme
    if (!ref.current || data.nodes.length === 0) return;
    const p = chartPalette();
    const maxImp = Math.max(...data.nodes.map((n) => n.data.importance), 1);
    const maxW = Math.max(...data.edges.map((e) => e.data.weight), 1);
    const cy = cytoscape({
      container: ref.current,
      elements: [
        ...data.nodes.map((n) => ({ ...n, data: { ...n.data, sizePct: n.data.importance / maxImp } })),
        ...data.edges,
      ],
      style: [
        {
          selector: "node",
          style: {
            "background-color": `mapData(sizePct, 0, 1, ${p.muted}, ${p.accent})`,
            label: "data(label)",
            color: p.text,
            "font-size": 11,
            "text-valign": "bottom",
            "text-halign": "center",
            "text-margin-y": 4,
            "text-outline-color": p.bg,
            "text-outline-width": 2,
            width: "mapData(sizePct, 0, 1, 14, 70)",
            height: "mapData(sizePct, 0, 1, 14, 70)",
            "border-width": "mapData(sizePct, 0, 1, 0, 2)",
            "border-color": p.accent2,
          },
        },
        {
          selector: "edge",
          style: {
            "line-color": p.border,
            "curve-style": "bezier",
            width: `mapData(weight, 1, ${maxW}, 1, 5)`,
            opacity: 0.55,
          },
        },
        {
          selector: "node:selected",
          style: { "border-color": p.warn, "border-width": 3 },
        },
      ],
      layout: {
        name: "cose",
        animate: false,
        idealEdgeLength: () => 100,
        nodeRepulsion: () => 12000,
        gravity: 30,
      } as any,
    });
    cy.on("tap", "node", (evt) => {
      const d = evt.target.data();
      console.log(d);
    });
    return () => { cy.destroy(); };
  }, [data, theme, colorScheme]);

  return (
    <div className="card">
      <div className="row" style={{ alignItems: "center", flexWrap: "wrap" }}>
        <h2 style={{ margin: 0 }}>
          人物关系网图 · {data.nodes.length} 节点 / {data.edges.length} 边
          {labeledEdges > 0 && (
            <span style={{ fontSize: 12, color: "var(--c-story)", marginLeft: 8, fontWeight: 400 }}>
              （{labeledEdges} 条已标注）
            </span>
          )}
        </h2>
        <span className="muted" style={{ marginLeft: 16 }}>显示</span>
        <select value={topN} onChange={(e) => setTopN(+e.target.value)}>
          <option value={20}>top 20</option>
          <option value={40}>top 40</option>
          <option value={60}>top 60</option>
          <option value={100}>top 100</option>
        </select>
        <button onClick={runTidy} disabled={extracting} style={{ marginLeft: "auto", padding: "4px 12px", fontSize: 12, background: "var(--accent)" }}
          title="多视角/多批次的书容易产生重复实体（同一角色多个名字），先合并去重、重算重要度，再抽关系。复杂的书强烈建议先点这个。">
          {extracting ? "整理中…" : "🧹 整理图谱（去重+重算+关系）"}
        </button>
        <button onClick={runExtract} disabled={extracting} style={{ padding: "4px 12px", fontSize: 12 }}>
          {extracting ? "…" : "🔍 仅抽关系"}
        </button>
      </div>
      {narrNote && (
        <div style={{ margin: "8px 0", padding: "8px 12px", borderRadius: 6, fontSize: 12,
                      background: "rgba(250,173,20,0.12)", border: "1px solid #faad14", color: "#d48806" }}>
          ⓘ {narrNote}
        </div>
      )}
      <p className="muted" style={{ marginBottom: 8 }}>
        {theme === "modern"
          ? "节点按角色配色（主角红 / 反派紫 / 盟友蓝 / 配角橙 / 龙套灰）。点击节点或边查看详情。"
          : "节点大小 / 颜色深浅 = 重要度。边权重 = 共同出现次数。"}
        {labeledEdges === 0 && " 边目前只显示共同出现，点上方按钮跑一次 LLM 抽取生成有标签的关系。"}
      </p>
      {msg && <p style={{ fontSize: 12, color: msg.startsWith("✅") ? "var(--good)" : "var(--bad)" }}>{msg}</p>}
      {theme === "modern" ? (
        <PersonFlowGraph nodes={data.nodes} edges={data.edges} height={720} />
      ) : (
        <div ref={ref} style={{ width: "100%", height: 720, background: "var(--panel-2)", borderRadius: 8 }} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// 主角演变 — 境界折线 + 物品/技能数 + hover 标注
// ---------------------------------------------------------------------------

function HeroEvolution() {
  const { colorScheme } = useTheme();
  const ref = useRef<HTMLDivElement | null>(null);
  const [data, setData] = useState<any>(null);

  useEffect(() => { api.hero().then(setData); }, []);

  // 归一化 realm 名：模型偶尔输出"一级封号魔导士（XX说明）"，提取主名。
  const cleanedSeries = useMemo(() => {
    if (!data?.series) return [];
    const cleanedRealmIdx: Record<string, number> = {};
    return data.series.map((s: any) => {
      let r: string | null = s.realm;
      if (r) {
        r = r.replace(/[（(].*?[)）]/g, "").replace(/\s*->\s*.*/, "").trim();
        if (!(r in cleanedRealmIdx)) cleanedRealmIdx[r] = Object.keys(cleanedRealmIdx).length;
      }
      return { ...s, realm_clean: r, realm_idx_clean: r ? cleanedRealmIdx[r] : null };
    });
  }, [data]);

  const realmNames = useMemo(() => {
    const idx: Record<string, number> = {};
    cleanedSeries.forEach((s: any) => {
      if (s.realm_clean && !(s.realm_clean in idx)) idx[s.realm_clean] = Object.keys(idx).length;
    });
    return Object.keys(idx);
  }, [cleanedSeries]);

  useEffect(() => {
    if (!ref.current || !data || cleanedSeries.length === 0) return;
    let chart: any;
    (async () => {
      const echarts = await import("echarts");
      chart = echarts.init(ref.current!);
      const p = chartPalette();
      chart.setOption({
        backgroundColor: "transparent",
        title: {
          text: data.hero?.name ? `主角：${data.hero.name}（importance=${data.hero?.importance}）` : "(无)",
          textStyle: { color: p.text, fontSize: 14 },
        },
        tooltip: {
          trigger: "axis",
          backgroundColor: p.panel,
          borderColor: p.border,
          textStyle: { color: p.text },
          formatter: (params: any) => {
            const idx = params[0].dataIndex;
            const s = cleanedSeries[idx];
            return `
              <b>第${s.chapter}章</b> ${s.chapter_title || ""}<br/>
              境界：<span style="color:${p.accent2}">${s.realm || "—"}</span><br/>
              物品：${s.items_count} · 技能：${s.skills_count}<br/>
              ${s.note ? `<div style="max-width:480px;white-space:normal;margin-top:6px;color:${p.good}">${s.note}</div>` : ""}
            `;
          },
        },
        legend: { textStyle: { color: p.text }, top: 24 },
        grid: { left: 60, right: 60, top: 70, bottom: 60 },
        xAxis: {
          type: "value",
          name: "章节",
          axisLabel: { color: p.muted },
          splitLine: { lineStyle: { color: p.border } },
        },
        yAxis: [
          {
            type: "value",
            name: "境界等级",
            min: 0,
            max: realmNames.length - 1,
            interval: 1,
            axisLabel: {
              color: p.accent2,
              fontSize: 10,
              formatter: (v: number) => realmNames[v] || "",
            },
          },
          { type: "value", name: "数量", axisLabel: { color: p.muted } },
        ],
        series: [
          {
            name: "境界",
            type: "line",
            step: "end",
            symbolSize: 6,
            data: cleanedSeries.map((s: any) => [s.chapter, s.realm_idx_clean]),
            lineStyle: { color: p.accent2, width: 3 },
            itemStyle: { color: p.accent2 },
            connectNulls: true,
          },
          {
            name: "物品数",
            type: "line",
            yAxisIndex: 1,
            data: cleanedSeries.map((s: any) => [s.chapter, s.items_count]),
            lineStyle: { color: p.accent },
            itemStyle: { color: p.accent },
            symbolSize: 4,
          },
          {
            name: "技能数",
            type: "line",
            yAxisIndex: 1,
            data: cleanedSeries.map((s: any) => [s.chapter, s.skills_count]),
            lineStyle: { color: p.good },
            itemStyle: { color: p.good },
            symbolSize: 4,
          },
        ],
      });
    })();
    return () => { chart?.dispose(); };
  }, [data, cleanedSeries, realmNames, colorScheme]);

  if (!data) return <div className="card">加载中…</div>;
  return (
    <div className="card">
      <h2>主角演变</h2>
      <p className="muted">{data.hero?.description}</p>
      <p className="muted" style={{ fontSize: 12 }}>
        境界等级序列：{realmNames.length === 0 ? "(无数据)" : realmNames.join(" → ")}
      </p>
      <div ref={ref} style={{ width: "100%", height: 520 }} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// 剧情时间线
// ---------------------------------------------------------------------------

function Timeline() {
  const [rows, setRows] = useState<any[]>([]);
  const [minImp, setMinImp] = useState(60);
  useEffect(() => {
    api.timeline(minImp).then(setRows).catch(() => {});
  }, [minImp]);

  return (
    <div className="card">
      <div className="row" style={{ alignItems: "center" }}>
        <h2 style={{ margin: 0 }}>剧情时间线 — {rows.length} 项</h2>
        <span className="muted" style={{ marginLeft: 16 }}>importance ≥</span>
        <select value={minImp} onChange={(e) => setMinImp(+e.target.value)}>
          <option value={50}>50</option>
          <option value={60}>60</option>
          <option value={70}>70</option>
          <option value={80}>80</option>
        </select>
      </div>
      <div style={{ position: "relative", marginTop: 16 }}>
        <div style={{ position: "absolute", left: 80, top: 0, bottom: 0, width: 2, background: "var(--border)" }} />
        {rows.map((r, i) => (
          <div key={i} style={{ display: "grid", gridTemplateColumns: "70px 16px 1fr", gap: 12, alignItems: "start", padding: "10px 0", position: "relative" }}>
            <div className="muted" style={{ fontSize: 12, textAlign: "right", paddingTop: 2 }}>第{r.chapter}章</div>
            <div style={{ position: "relative", height: 16 }}>
              <div style={{
                position: "absolute", left: 4, top: 5, width: 10, height: 10, borderRadius: "50%",
                background: r.importance >= 80 ? "#bb9af7" : r.importance >= 70 ? "#7aa2f7" : "#7dcfff",
                boxShadow: r.importance >= 80 ? "0 0 0 3px rgba(187,154,247,.25)" : "none",
              }} />
            </div>
            <div>
              <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 2 }}>
                <span className="tag">imp {r.importance}</span> {r.chapter_title}
              </div>
              <div style={{ fontSize: 13 }}>{r.summary}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
