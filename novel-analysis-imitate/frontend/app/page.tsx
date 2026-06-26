"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import Chart from "@/components/Chart";

// 颜料盘:铺垫=赭石,高潮系=朱砂深浅,悬疑=黛,煽情=石青,日常/转场=暗赭灰
const SCENE_COLORS: Record<string, string> = {
  铺垫: "#be8a3c", 小高潮: "#d76b52", 大高潮: "#c8442e", 热血: "#cf5a36",
  悬疑惊悚: "#7d80b4", 煽情: "#4e8597", 日常: "#8c806a", 转场: "#5a4f3c", 其他: "#6b5f49",
};
const POV_PALETTE = ["#4e8597", "#be8a3c", "#7d80b4", "#c8442e", "#8c806a", "#5a8a72", "#a8763a", "#9a8e76"];
const C = { ink: "#14110d", rule: "#3a3022", ruleSoft: "#2c2419", qing: "#4e8597", zhu: "#c8442e", zhe: "#be8a3c", dai: "#7d80b4", bone: "#b9ad96" };

const TABS = [
  { k: "pacing", t: "节拍 · 张力曲线" },
  { k: "worldview", t: "世界观铺垫" },
  { k: "relationship", t: "人物关系" },
  { k: "pov", t: "视角调度" },
  { k: "golden", t: "金手指升级" },
];

export default function Page() {
  const [books, setBooks] = useState<any[]>([]);
  const [slug, setSlug] = useState("");
  const [data, setData] = useState<any>(null);
  const [tab, setTab] = useState("pacing");
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [maxCh, setMaxCh] = useState<string>("");
  const [msg, setMsg] = useState("");

  useEffect(() => {
    api.books().then((bs) => {
      setBooks(bs);
      if (bs[0]) setSlug(bs[0].slug);
    }).catch((e) => setMsg("无法连接后端 :8100 — " + e.message));
  }, []);

  async function load() {
    if (!slug) return;
    setLoading(true); setMsg("");
    try { setData(await api.analysis(slug)); }
    catch (e: any) { setMsg("拉取分析失败: " + e.message); }
    finally { setLoading(false); }
  }
  useEffect(() => { if (slug) load(); /* eslint-disable-next-line */ }, [slug]);

  async function runAnalysis() {
    if (!slug) return;
    setRunning(true); setMsg("已在后台启动全分析层(串行,可能数分钟)。可稍后点『刷新』查看。");
    try {
      await api.analyzeBook(slug, { max_chapters: maxCh ? Number(maxCh) : undefined });
    } catch (e: any) { setMsg("启动失败: " + e.message); }
    finally { setRunning(false); }
  }

  return (
    <div className="wrap">
      <span className="eyebrow">CRAFT · DNA</span>
      <div className="h1">逐章拆解一本书的叙事脉象</div>
      <div className="sub">张力节拍 · 世界观铺垫 · 视角调度 · 人物关系 · 金手指曲线 —— 把长篇小说的隐藏机理摊开成可读的刻度。</div>

      <div className="card">
        <div className="row">
          <select value={slug} onChange={(e) => setSlug(e.target.value)}>
            {books.map((b) => <option key={b.slug} value={b.slug}>{b.title || b.slug}</option>)}
          </select>
          <button className="btn ghost" onClick={load} disabled={loading}>{loading ? "加载中…" : "刷新"}</button>
          <span style={{ flex: 1 }} />
          <input placeholder="限N章(留空=全书)" value={maxCh}
            onChange={(e) => setMaxCh(e.target.value.replace(/\D/g, ""))}
            style={{ width: 150 }} />
          <button className="btn" onClick={runAnalysis} disabled={running}>运行分析</button>
        </div>
        {msg && <div className="muted" style={{ marginTop: 10, fontSize: 13 }}>{msg}</div>}
      </div>

      <div className="tabs">
        {TABS.map((x) => (
          <div key={x.k} className={"tab" + (tab === x.k ? " active" : "")} onClick={() => setTab(x.k)}>{x.t}</div>
        ))}
      </div>

      {!data ? <div className="empty">选择书籍后将展示分析结果</div> : (
        <>
          {tab === "pacing" && <Pacing d={data.beats} />}
          {tab === "worldview" && <Worldview d={data.worldview} />}
          {tab === "relationship" && <Relationship d={data.relationships} />}
          {tab === "pov" && <Pov d={data.pov} />}
          {tab === "golden" && <Golden d={data.golden} />}
        </>
      )}
    </div>
  );
}

function Stat({ v, k }: { v: any; k: string }) {
  return <div className="stat"><div className="v">{v}</div><div className="k">{k}</div></div>;
}

function Pacing({ d }: { d: any }) {
  const beats = d?.beats || [];
  const card = d?.pacing_card;
  if (!beats.length) return <Empty layer="节拍" />;
  const xs = beats.map((b: any) => b.chapter);
  const option = {
    grid: { left: 45, right: 20, top: 30, bottom: 40 },
    legend: { data: ["张力", "章末钩子"], textStyle: { color: C.bone }, top: 0 },
    tooltip: {
      trigger: "axis",
      formatter: (ps: any[]) => {
        const i = ps[0].dataIndex; const b = beats[i];
        return `第${b.chapter}章 [${b.scene_type}]<br/>张力 ${b.tension} · 钩子 ${b.cliffhanger}<br/>POV: ${b.pov_holder}${b.is_protagonist_pov ? "(主角)" : ""}<br/><span style="color:#8b96a8">${b.summary || ""}</span>`;
      },
    },
    xAxis: { type: "category", data: xs, name: "章", axisLine: { lineStyle: { color: C.rule } } },
    yAxis: { type: "value", max: 100, splitLine: { lineStyle: { color: C.ruleSoft } } },
    series: [
      {
        name: "张力", type: "line", smooth: true, data: beats.map((b: any) => b.tension),
        lineStyle: { width: 2, color: C.qing }, areaStyle: { color: "rgba(78,133,151,0.13)" },
        itemStyle: { color: (p: any) => SCENE_COLORS[beats[p.dataIndex].scene_type] || C.qing }, symbolSize: 6,
      },
      {
        name: "章末钩子", type: "bar", data: beats.map((b: any) => b.cliffhanger),
        itemStyle: { color: "rgba(200,68,46,0.42)" }, barWidth: "40%",
      },
    ],
  };
  const dist = card?.scene_distribution || {};
  const pie = {
    tooltip: { trigger: "item" },
    legend: { type: "scroll", bottom: 0, textStyle: { color: C.bone } },
    series: [{
      type: "pie", radius: ["35%", "65%"], center: ["50%", "45%"],
      data: Object.entries(dist).map(([k, v]) => ({ name: k, value: v, itemStyle: { color: SCENE_COLORS[k] } })),
      label: { color: C.bone },
    }],
  };
  return (
    <>
      <div className="card">
        <h2>逐章张力曲线 <span className="tag">点色=场景类型,柱=章末钩子强度</span></h2>
        {card && <div className="stat-row" style={{ marginBottom: 14 }}>
          <Stat v={card.n_chapters} k="章数" />
          <Stat v={card.tension_avg} k="平均张力" />
          <Stat v={card.tension_max} k="峰值张力" />
          <Stat v={`${Math.round(card.protagonist_pov_ratio * 100)}%`} k="主角视角占比" />
          <Stat v={card.avg_cliffhanger} k="平均钩子强度" />
          <Stat v={(card.big_climax_chapters || []).length} k="大高潮章数" />
        </div>}
        <Chart option={option} height={340} />
      </div>
      <div className="card">
        <h2>场景类型分布</h2>
        <Chart option={pie} height={300} />
      </div>
    </>
  );
}

function Worldview({ d }: { d: any }) {
  const rv = d?.reveals || [];
  const card = d?.worldview_card;
  if (!rv.length) return <Empty layer="世界观揭示" />;
  const scatter = {
    grid: { left: 45, right: 20, top: 20, bottom: 40 },
    tooltip: {
      trigger: "item",
      formatter: (p: any) => {
        const r = rv[p.dataIndex];
        return `第${r.chapter}章 · ${r.concept}<br/>手法: ${r.reveal_method}${r.is_infodump ? " · ⚠信息倾倒" : ""}<br/>重要度 ${r.importance}<br/><span style="color:#8b96a8">${r.summary || ""}</span>`;
      },
    },
    xAxis: { type: "value", name: "章", axisLine: { lineStyle: { color: C.rule } } },
    yAxis: { type: "value", name: "重要度", max: 100, splitLine: { lineStyle: { color: C.ruleSoft } } },
    series: [{
      type: "scatter",
      data: rv.map((r: any) => [r.chapter, r.importance]),
      symbolSize: (_: any, p: any) => 8 + (rv[p.dataIndex].importance / 12),
      itemStyle: { color: (p: any) => rv[p.dataIndex].is_infodump ? C.zhu : C.qing, opacity: 0.9 },
    }],
  };
  const md = card?.reveal_method_distribution || {};
  const bar = {
    grid: { left: 70, right: 20, top: 10, bottom: 30 },
    tooltip: { trigger: "axis" },
    xAxis: { type: "value", splitLine: { lineStyle: { color: C.ruleSoft } } },
    yAxis: { type: "category", data: Object.keys(md), axisLine: { lineStyle: { color: C.rule } } },
    series: [{ type: "bar", data: Object.values(md), itemStyle: { color: C.dai }, barWidth: "55%" }],
  };
  return (
    <>
      <div className="card">
        <h2>世界观铺垫节奏 <span className="tag">蓝=自然融入,橙=信息倾倒;点大小∝重要度</span></h2>
        {card && <div className="stat-row" style={{ marginBottom: 14 }}>
          <Stat v={card.n_reveals} k="揭示总数" />
          <Stat v={`${Math.round(card.infodump_ratio * 100)}%`} k="信息倾倒率" />
          <Stat v={card.avg_setup_payoff_gap} k="平均埋设跨度(章)" />
          <Stat v={`${Math.round(card.front_loaded_ratio * 100)}%`} k="前1/4篇幅承载" />
        </div>}
        <Chart option={scatter} height={320} />
      </div>
      <div className="card"><h2>揭示手法分布</h2><Chart option={bar} height={260} /></div>
      <div className="card">
        <h2>重大设定揭示</h2>
        <table><thead><tr><th>章</th><th>设定</th><th>手法</th><th>重要度</th><th>摘要</th></tr></thead>
          <tbody>{rv.slice().sort((a: any, b: any) => b.importance - a.importance).slice(0, 15).map((r: any, i: number) => (
            <tr key={i}><td>{r.chapter}</td><td>{r.concept}</td>
              <td>{r.reveal_method}{r.is_infodump ? <span className="pill dump">倾倒</span> : null}</td>
              <td>{r.importance}</td><td className="muted">{r.summary}</td></tr>
          ))}</tbody></table>
      </div>
    </>
  );
}

function Relationship({ d }: { d: any }) {
  const ev = d?.events || [];
  const tracks = d?.tracks || {};
  const card = d?.relationship_card;
  if (!ev.length) return <Empty layer="关系演变" />;
  return (
    <>
      <div className="card">
        <h2>关系演变概览</h2>
        {card && <div className="stat-row" style={{ marginBottom: 8 }}>
          <Stat v={card.n_events} k="转变事件数" />
          <Stat v={card.n_pairs} k="涉及关系对" />
        </div>}
        <div style={{ marginTop: 6 }}>
          {(card?.most_dynamic_pairs || []).map((p: any, i: number) => (
            <span key={i} className="pill">{p.pair} · {p.changes}次转变</span>
          ))}
        </div>
      </div>
      <div className="card">
        <h2>关系轨迹</h2>
        {Object.entries(tracks).map(([pair, evs]: any, i: number) => (
          <div key={i} style={{ marginBottom: 10 }}>
            <b style={{ fontSize: 13 }}>{pair}</b>{" "}
            {evs.map((e: any, j: number) => (
              <span key={j} className="pill">第{e.chapter}章→{e.state}</span>
            ))}
          </div>
        ))}
      </div>
      <div className="card">
        <h2>转变明细</h2>
        <table><thead><tr><th>章</th><th>关系</th><th>新状态</th><th>触发</th></tr></thead>
          <tbody>{ev.map((e: any, i: number) => (
            <tr key={i}><td>{e.chapter}</td><td>{e.a} — {e.b}</td><td>{e.state}</td><td className="muted">{e.trigger}</td></tr>
          ))}</tbody></table>
      </div>
    </>
  );
}

function Pov({ d }: { d: any }) {
  const tl = d?.timeline || [];
  const card = d?.pov_card;
  const ev = d?.events || [];
  if (!tl.length) return <Empty layer="视角(需先跑节拍层)" />;
  const holders = Array.from(new Set(tl.map((t: any) => t.pov_holder)));
  const colorOf = (h: string) => POV_PALETTE[holders.indexOf(h) % POV_PALETTE.length];
  return (
    <>
      <div className="card">
        <h2>视角调度</h2>
        {card && <div className="stat-row" style={{ marginBottom: 14 }}>
          <Stat v={card.switch_count} k="视角切换次数" />
          <Stat v={`${Math.round(card.nonprotagonist_pov_ratio * 100)}%`} k="配角视角占比" />
          <Stat v={card.avg_away_span} k="离主视角平均时长(章)" />
          <Stat v={card.distinct_pov_holders} k="不同视角人物" />
        </div>}
        <div style={{ display: "flex", flexWrap: "wrap" }}>
          {tl.map((t: any, i: number) => (
            <span key={i} className="povcell" title={`第${t.chapter}章 · ${t.pov_holder}${t.is_protagonist_pov ? "(主角)" : ""}`}
              style={{ background: colorOf(t.pov_holder), opacity: t.is_protagonist_pov ? 1 : 0.55 }} />
          ))}
        </div>
        <div style={{ marginTop: 12 }}>
          {holders.map((h: any, i: number) => (
            <span key={i} className="pill" style={{ borderColor: colorOf(h) }}>
              <span className="povcell" style={{ background: colorOf(h), verticalAlign: "middle", marginRight: 5 }} />{h}
            </span>
          ))}
        </div>
      </div>
      <div className="card">
        <h2>切换事件</h2>
        <table><thead><tr><th>章</th><th>由→至</th><th>动机</th><th>几章后回主视角</th></tr></thead>
          <tbody>{ev.map((e: any, i: number) => (
            <tr key={i}><td>{e.chapter}</td><td>{e.from_pov} → {e.to_pov}</td><td>{e.why_switch}</td>
              <td>{e.return_after || "—"}</td></tr>
          ))}</tbody></table>
      </div>
    </>
  );
}

function Golden({ d }: { d: any }) {
  const steps = d?.steps || [];
  const card = d?.golden_card;
  if (!steps.length) return <Empty layer="金手指升级(早期慢热可能为空)" />;
  return (
    <>
      <div className="card">
        <h2>升级斜率</h2>
        {card && <div className="stat-row" style={{ marginBottom: 14 }}>
          <Stat v={card.n_steps} k="升级台阶数" />
          <Stat v={card.avg_chapters_per_upgrade} k="平均每级间隔(章)" />
        </div>}
        <div>{Object.entries(card?.trigger_distribution || {}).map(([k, v]: any, i) => (
          <span key={i} className="pill">{k}:{v}</span>
        ))}</div>
      </div>
      <div className="card">
        <h2>升级台阶</h2>
        <table><thead><tr><th>章</th><th>境界/档位</th><th>新能力</th><th>触发</th><th>对手差距</th></tr></thead>
          <tbody>{steps.map((s: any, i: number) => (
            <tr key={i}><td>{s.chapter}</td><td>{s.power_tier}</td><td>{s.new_capability}</td>
              <td>{s.trigger}</td><td>{s.gap_vs_antagonist}</td></tr>
          ))}</tbody></table>
      </div>
    </>
  );
}

function Empty({ layer }: { layer: string }) {
  return <div className="card"><div className="empty">暂无「{layer}」数据 — 点上方『运行分析』后刷新</div></div>;
}
