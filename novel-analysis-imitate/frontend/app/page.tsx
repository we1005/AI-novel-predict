"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import Chart from "@/components/Chart";
import dynamic from "next/dynamic";
const RelationGraph = dynamic(() => import("@/components/RelationGraph"), { ssr: false });

// 颜料盘(亮底):铺垫=赭石,高潮系=朱砂深浅,悬疑=黛,煽情=石青,日常/转场=暖灰
const SCENE_COLORS: Record<string, string> = {
  铺垫: "#9a6b2f", 小高潮: "#cf6b4a", 大高潮: "#c0392b", 热血: "#c8552f",
  悬疑惊悚: "#565a8c", 煽情: "#2e6f80", 日常: "#8a8270", 转场: "#b3a98f", 其他: "#a0957c",
};
const POV_PALETTE = ["#2e6f80", "#9a6b2f", "#565a8c", "#c0392b", "#7a8a6a", "#8a8270", "#b07a35", "#6b7b8a"];
const C = { paper: "#f1efe5", rule: "#d6d0bf", ruleSoft: "#e6e1d1", qing: "#2e6f80", zhu: "#c0392b", zhe: "#9a6b2f", dai: "#565a8c", bone: "#574f40" };

const TABS = [
  { k: "speedread", t: "速读 · 剧情脉络" },
  { k: "pacing", t: "节拍 · 张力曲线" },
  { k: "style", t: "文笔 · 声音" },
  { k: "worldview", t: "世界观铺垫" },
  { k: "relationship", t: "人物关系" },
  { k: "settings", t: "设定 · 伏笔" },
  { k: "pov", t: "视角调度" },
  { k: "golden", t: "金手指升级" },
];

export default function Page() {
  const [books, setBooks] = useState<any[]>([]);
  const [slug, setSlug] = useState("");
  const [data, setData] = useState<any>(null);
  const [tab, setTab] = useState("pacing");
  const [view, setView] = useState<"chart" | "text">("chart");
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [maxCh, setMaxCh] = useState<string>("");
  const [msg, setMsg] = useState("");

  useEffect(() => {
    api.books().then((bs) => {
      setBooks(bs);
      // 默认选第一本「已分析」的书,避免一进来就是空页
      const first = bs.find((b: any) => b.analyzed) || bs[0];
      if (first) setSlug(first.slug);
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

      <div className="layout">
        <aside className="side">
          <select value={slug} onChange={(e) => setSlug(e.target.value)} style={{ width: "100%" }}>
            {books.map((b) => <option key={b.slug} value={b.slug}>
              {b.analyzed ? "● " : "○ "}{b.title || b.slug}{b.analyzed ? ` (${b.n_beats}章)` : " · 未分析"}
            </option>)}
          </select>

          <nav className="sidetabs">
            {TABS.map((x) => (
              <div key={x.k} className={"sidetab" + (tab === x.k ? " active" : "")} onClick={() => setTab(x.k)}>{x.t}</div>
            ))}
          </nav>

          <div className="sidegroup">
            <div className="sidelabel">视图</div>
            <div className="viewtoggle" style={{ width: "100%" }}>
              {(["chart", "text"] as const).map((v) => (
                <span key={v} className={"vbtn" + (view === v ? " on" : "")} style={{ flex: 1, textAlign: "center" }} onClick={() => setView(v)}>
                  {v === "chart" ? "图表" : "文字"}
                </span>
              ))}
            </div>
          </div>

          <div className="sidegroup">
            <div className="sidelabel">操作</div>
            <button className="btn ghost" onClick={load} disabled={loading} style={{ width: "100%", marginBottom: 8 }}>{loading ? "加载中…" : "刷新"}</button>
            <input placeholder="限N章(留空=全书)" value={maxCh}
              onChange={(e) => setMaxCh(e.target.value.replace(/\D/g, ""))}
              style={{ width: "100%", marginBottom: 8 }} />
            <button className="btn" onClick={runAnalysis} disabled={running} style={{ width: "100%" }}>运行分析</button>
            {msg && <div className="muted" style={{ marginTop: 10, fontSize: 12.5, lineHeight: 1.6 }}>{msg}</div>}
          </div>
        </aside>

        <main className="main">
          {!data ? <div className="empty">选择书籍后将展示分析结果</div> : (
            <>
              {tab === "speedread" && <SpeedRead d={data.speedread} slug={slug} />}
              {tab === "pacing" && <Pacing d={data.beats} view={view} />}
              {tab === "style" && <Style d={data.style} />}
              {tab === "worldview" && <Worldview d={data.worldview} view={view} />}
              {tab === "relationship" && <Relationship d={data.relationships} chars={data.characters} slug={slug} view={view} />}
              {tab === "settings" && <Settings d={data.base} slug={slug} />}
              {tab === "pov" && <Pov d={data.pov} view={view} />}
              {tab === "golden" && <Golden d={data.golden} />}
            </>
          )}
        </main>
      </div>
    </div>
  );
}

function Stat({ v, k }: { v: any; k: string }) {
  return <div className="stat"><div className="v">{v}</div><div className="k">{k}</div></div>;
}

function Pacing({ d, view }: { d: any; view: string }) {
  const beats = d?.beats || [];
  const card = d?.pacing_card;
  if (!beats.length) return <Empty layer="节拍" />;
  if (view === "text") return (
    <div className="card">
      <h2>逐章节拍 <span className="tag">{beats.length} 章</span></h2>
      <div className="tablescroll"><table>
        <thead><tr><th>章</th><th>场景</th><th>张力</th><th>钩子</th><th>功能</th><th>POV</th><th>节拍摘要</th></tr></thead>
        <tbody>{beats.map((b: any) => (
          <tr key={b.chapter}>
            <td>{b.chapter}</td>
            <td><span className="scenechip" style={{ background: SCENE_COLORS[b.scene_type] || "#999" }} />{b.scene_type}</td>
            <td>{b.tension}</td><td>{b.cliffhanger}</td><td className="muted">{b.plot_function}</td>
            <td>{b.pov_holder}{b.is_protagonist_pov ? "" : "·配"}</td>
            <td className="muted">{b.summary}</td>
          </tr>
        ))}</tbody>
      </table></div>
    </div>
  );
  const xs = beats.map((b: any) => b.chapter);
  const option = {
    grid: { left: 45, right: 20, top: 30, bottom: 40 },
    legend: { data: ["张力", "章末钩子"], textStyle: { color: C.bone }, top: 0 },
    tooltip: {
      trigger: "axis",
      formatter: (ps: any[]) => {
        const i = ps[0].dataIndex; const b = beats[i];
        return `第${b.chapter}章 [${b.scene_type}]<br/>张力 ${b.tension} · 钩子 ${b.cliffhanger}<br/>POV: ${b.pov_holder}${b.is_protagonist_pov ? "(主角)" : ""}<br/><span style="color:#8a8270">${b.summary || ""}</span>`;
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

function Worldview({ d, view }: { d: any; view: string }) {
  const rv = d?.reveals || [];
  const card = d?.worldview_card;
  if (!rv.length) return <Empty layer="世界观揭示" />;
  if (view === "text") return (
    <div className="card">
      <h2>世界观揭示逐条 <span className="tag">{rv.length} 条 · 按章序</span></h2>
      <div className="tablescroll"><table>
        <thead><tr><th>章</th><th>设定/概念</th><th>手法</th><th>重要度</th><th>说明</th></tr></thead>
        <tbody>{rv.map((r: any, i: number) => (
          <tr key={i}><td>{r.chapter}</td><td>{r.concept}</td>
            <td>{r.reveal_method}{r.is_infodump ? <span className="pill dump">倒灌</span> : null}</td>
            <td>{r.importance}</td><td className="muted">{r.summary}</td></tr>
        ))}</tbody>
      </table></div>
    </div>
  );
  const scatter = {
    grid: { left: 45, right: 20, top: 20, bottom: 40 },
    tooltip: {
      trigger: "item",
      formatter: (p: any) => {
        const r = rv[p.dataIndex];
        return `第${r.chapter}章 · ${r.concept}<br/>手法: ${r.reveal_method}${r.is_infodump ? " · ⚠信息倾倒" : ""}<br/>重要度 ${r.importance}<br/><span style="color:#8a8270">${r.summary || ""}</span>`;
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

function CharCards({ chars, slug }: { chars: any; slug: string }) {
  const list = chars?.characters || [];
  const [msg, setMsg] = useState("");
  async function run() {
    setMsg("已后台生成人物卡(据关系/出场判定主要人物,约1-2分钟)。稍后点侧栏『刷新』。");
    try { await fetch(`/api/books/${encodeURIComponent(slug)}/characters`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }); }
    catch (e: any) { setMsg("启动失败: " + e.message); }
  }
  if (!list.length) return (
    <div className="card">
      <h2>主要人物</h2>
      <div className="muted" style={{ marginBottom: 10 }}>还没有人物卡 — 据关系/出场自动判定重要人物并生成简介。</div>
      <button className="btn" onClick={run}>生成人物卡</button>
      {msg && <div className="muted" style={{ marginTop: 10, fontSize: 13 }}>{msg}</div>}
    </div>
  );
  return (
    <div className="card">
      <span className="eyebrow">DRAMATIS PERSONAE</span>
      <h2>主要人物 <span className="tag">{list.length} 位 · 按重要度</span></h2>
      <div className="charscroll">
        {list.map((c: any) => (
          <div key={c.name} className="charcard">
            <div className="charhead">
              <span className="charname">{c.name}</span>
              {c.role && <span className="rolebadge">{c.role}</span>}
            </div>
            <div className="impbar"><span style={{ width: `${c.importance}%` }} /></div>
            {c.one_line && <div className="charone">{c.one_line}</div>}
            {c.description && <p className="chardesc">{c.description}</p>}
            {c.personality && <p className="chardesc"><b>性格动机</b>:{c.personality}</p>}
            {c.arc && <p className="chardesc" style={{ color: "var(--zhu-deep)" }}><b>弧光</b>:{c.arc}</p>}
            {!!(c.key_relations || []).length && (
              <div style={{ marginTop: 6 }}>
                {c.key_relations.slice(0, 5).map((r: any, i: number) => (
                  <span key={i} className="pill">{typeof r === "string" ? r : `${r.who}·${r.relation}`}</span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function Relationship({ d, chars, slug, view }: { d: any; chars: any; slug: string; view: string }) {
  const ev = d?.events || [];
  const tracks = d?.tracks || {};
  const card = d?.relationship_card;
  if (!ev.length) return <Empty layer="关系演变" />;
  return (
    <>
      <CharCards chars={chars} slug={slug} />
      <div className="card">
        <h2>关系演变概览 <span className="tag">{view === "chart" ? "节点=人物,边=关系(色:红=对立/青=亲密),可缩放拖拽" : "逐条表格"}</span></h2>
        {card && <div className="stat-row" style={{ marginBottom: 8 }}>
          <Stat v={card.n_events} k="转变事件数" />
          <Stat v={card.n_pairs} k="涉及关系对" />
        </div>}
        <div style={{ marginTop: 6 }}>
          {(card?.most_dynamic_pairs || []).slice(0, 8).map((p: any, i: number) => (
            <span key={i} className="pill">{p.pair} · {p.changes}次</span>
          ))}
        </div>
      </div>

      {view === "chart" ? (
        <div className="card">
          <h2>关系网络图</h2>
          <RelationGraph tracks={tracks} />
        </div>
      ) : (
        <>
          <div className="card">
            <h2>关系轨迹 <span className="tag">{Object.keys(tracks).length} 对</span></h2>
            <div className="tablescroll" style={{ padding: "4px 10px" }}>
              {Object.entries(tracks).map(([pair, evs]: any, i: number) => (
                <div key={i} style={{ marginBottom: 9 }}>
                  <b style={{ fontSize: 13 }}>{pair}</b>{" "}
                  {evs.map((e: any, j: number) => (
                    <span key={j} className="pill">第{e.chapter}章→{e.state}</span>
                  ))}
                </div>
              ))}
            </div>
          </div>
          <div className="card">
            <h2>转变明细 <span className="tag">{ev.length}</span></h2>
            <div className="tablescroll"><table>
              <thead><tr><th>章</th><th>关系</th><th>新状态</th><th>触发</th></tr></thead>
              <tbody>{ev.map((e: any, i: number) => (
                <tr key={i}><td>{e.chapter}</td><td>{e.a} — {e.b}</td><td>{e.state}</td><td className="muted">{e.trigger}</td></tr>
              ))}</tbody></table></div>
          </div>
        </>
      )}
    </>
  );
}

function Pov({ d, view }: { d: any; view: string }) {
  const tl = d?.timeline || [];
  const card = d?.pov_card;
  const ev = d?.events || [];
  if (!tl.length) return <Empty layer="视角(需先跑节拍层)" />;
  if (view === "text") return (
    <div className="card">
      <h2>视角切换逐条 <span className="tag">{ev.length} 次切换</span></h2>
      <div className="tablescroll"><table>
        <thead><tr><th>章</th><th>由 → 至</th><th>动机</th><th>几章后回主视角</th><th>说明</th></tr></thead>
        <tbody>{ev.map((e: any, i: number) => (
          <tr key={i}><td>{e.chapter}</td><td>{e.from_pov} → {e.to_pov}</td>
            <td>{e.why_switch}</td><td>{e.return_after || "—"}</td><td className="muted">{e.summary}</td></tr>
        ))}</tbody>
      </table></div>
    </div>
  );
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

function SpeedRead({ d, slug }: { d: any; slug: string }) {
  const stages = d?.stages || [];
  const [open, setOpen] = useState<Record<number, boolean>>({});
  const [msg, setMsg] = useState("");
  async function run() {
    setMsg("已在后台启动速读(切阶段+重要阶段详写,约数分钟)。稍后点上方『刷新』查看。");
    try { await api.runSpeedread(slug); } catch (e: any) { setMsg("启动失败: " + e.message); }
  }
  if (!stages.length) return (
    <div className="card"><div className="empty">还没有速读 — 需先有节拍层,然后生成速读。</div>
      <div style={{ textAlign: "center" }}><button className="btn" onClick={run}>生成速读</button></div>
      {msg && <div className="muted" style={{ marginTop: 10, fontSize: 13, textAlign: "center" }}>{msg}</div>}
    </div>
  );
  const fld = (v: any) => Array.isArray(v) ? v : (v ? [v] : []);
  const DETAIL: [string, string][] = [
    ["what_happened", "发生了什么"], ["plot", "主线推进"], ["turns", "转折 / 高潮"],
    ["foreshadowing", "伏笔"], ["character_inner", "人物内心"], ["interactions", "互动 / 关系"], ["threads", "长期线索"],
  ];
  return (
    <>
      <div className="card">
        <span className="eyebrow">SPEED READ</span>
        <h2>剧情脉络速读 <span className="tag">{stages.length} 个阶段 · 朱砂=重要阶段(已详写)</span></h2>
        <div className="muted" style={{ fontSize: 13 }}>按章序通读全书走向;重要阶段展开看发生/铺垫/内心/转折。</div>
        <div style={{ textAlign: "right" }}><button className="btn ghost" onClick={run}>重跑速读</button></div>
        {msg && <div className="muted" style={{ marginTop: 8, fontSize: 13 }}>{msg}</div>}
      </div>
      {stages.map((s: any) => {
        const hot = (s.importance || 0) >= 4;
        const hasDetail = s.detail && Object.keys(s.detail).length > 0;
        return (
          <div key={s.stage_index} className="card"
            style={{ borderLeft: `3px solid ${hot ? "var(--zhu)" : s.importance >= 3 ? "var(--zhe)" : "var(--rule)"}` }}>
            <div className="row" style={{ justifyContent: "space-between", alignItems: "baseline" }}>
              <h2 style={{ margin: 0 }}>
                <span className="muted" style={{ fontFamily: "var(--mono)", fontSize: 13 }}>
                  第{s.chapter_start}-{s.chapter_end}章
                </span>{"  "}{s.title}
                <span style={{ color: "var(--zhu)", marginLeft: 8, fontSize: 13 }}>{"●".repeat(s.importance || 1)}</span>
              </h2>
              <span className="muted" style={{ fontSize: 12 }}>峰值张力 {s.peak_tension}</span>
            </div>
            <p style={{ margin: "8px 0 0", lineHeight: 1.75, fontSize: 14 }}>{s.one_liner}</p>
            {hasDetail && (
              <>
                <div style={{ marginTop: 8 }}>
                  <span className="vbtn on" style={{ cursor: "pointer", borderRadius: 2 }}
                    onClick={() => setOpen({ ...open, [s.stage_index]: !open[s.stage_index] })}>
                    {open[s.stage_index] ? "收起精读 ▲" : "展开精读 ▼"}
                  </span>
                </div>
                {open[s.stage_index] && (
                  <div style={{ marginTop: 12, borderTop: "1px solid var(--rule-soft)", paddingTop: 12 }}>
                    {DETAIL.map(([k, label]) => {
                      const items = fld(s.detail[k]);
                      if (!items.length) return null;
                      return (
                        <div key={k} style={{ marginBottom: 12 }}>
                          <div className="eyebrow" style={{ marginBottom: 4 }}>{label}</div>
                          {items.length > 1
                            ? <ul style={{ margin: 0, paddingLeft: 18, lineHeight: 1.75, fontSize: 13.5 }}>
                                {items.map((x: any, i: number) => <li key={i}>{typeof x === "string" ? x : JSON.stringify(x)}</li>)}
                              </ul>
                            : <div style={{ lineHeight: 1.75, fontSize: 13.5 }}>{typeof items[0] === "string" ? items[0] : JSON.stringify(items[0])}</div>}
                        </div>
                      );
                    })}
                  </div>
                )}
              </>
            )}
          </div>
        );
      })}
    </>
  );
}

function Style({ d }: { d: any }) {
  if (!d || !d.has_profile) return <Empty layer="文笔(尚未分析,点上方『运行分析』会一并跑文笔)" />;
  const asText = (v: any) => Array.isArray(v) ? v.join("、") : (typeof v === "object" && v ? JSON.stringify(v) : (v ?? "—"));
  const rows: [string, any][] = [
    ["整体声音", d.overall_voice], ["叙事视角", d.narrative_pov], ["句式节奏", d.sentence_rhythm],
    ["语域", d.register], ["叙事结构", d.narrative_structure], ["结构习惯", d.structural_habits],
  ];
  const vocab: string[] = Array.isArray(d.signature_vocabulary) ? d.signature_vocabulary
    : (d.signature_vocabulary ? String(d.signature_vocabulary).split(/[,，、\s]+/).filter(Boolean) : []);
  const tropes: string[] = Array.isArray(d.tropes) ? d.tropes
    : (d.tropes ? String(d.tropes).split(/[,，、；;\n]+/).filter(Boolean) : []);
  const ex = d.scene_exemplars || [];
  return (
    <>
      <div className="card">
        <span className="eyebrow">VOICE</span>
        <h2>文笔画像 <span className="tag">复用续写内核同款 StyleProfile,生成时即据此仿写</span></h2>
        {d.summary && <p style={{ lineHeight: 1.8, fontSize: 14.5, color: "var(--ink)" }}>{d.summary}</p>}
        <table><tbody>
          {rows.map(([k, v]) => <tr key={k}><th style={{ width: 110 }}>{k}</th><td>{asText(v)}</td></tr>)}
        </tbody></table>
      </div>
      {!!vocab.length && <div className="card"><h2>标志性词汇 / 意象 <span className="tag">{vocab.length}</span></h2>
        <div>{vocab.slice(0, 60).map((w, i) => <span key={i} className="pill">{w}</span>)}</div></div>}
      {!!tropes.length && <div className="card"><h2>套路 / 惯用手法</h2>
        <div>{tropes.map((w, i) => <span key={i} className="pill">{w}</span>)}</div></div>}
      {!!ex.length && <div className="card"><h2>文风范文 <span className="tag">逐字摘录,仿写 few-shot 用</span></h2>
        {ex.map((e: any, i: number) => (
          <div key={i} style={{ marginBottom: 12 }}>
            {e.scene && <div className="eyebrow" style={{ color: "var(--qing, #2e6f80)" }}>{e.scene}</div>}
            <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.85, fontSize: 14, fontFamily: "var(--serif)" }}>{typeof e.text === "string" ? e.text : JSON.stringify(e.text)}</div>
          </div>
        ))}</div>}
      {!!d.n_craft_cards && <div className="card"><h2>笔法拆解 <span className="tag">{d.n_craft_cards} 类</span></h2>
        <div>{d.craft_cards.map((c: any, i: number) => <span key={i} className="pill">{c.category} ({c.snippet_count})</span>)}</div></div>}
    </>
  );
}

function Settings({ d, slug }: { d: any; slug: string }) {
  const world = d?.world_rules || [];
  const fore = d?.foreshadowings || [];
  const plot = d?.plot_points || [];
  const [msg, setMsg] = useState("");
  async function run() {
    setMsg("已后台跑基础抽取(实体/伏笔/剧情点/世界规则/关系,复用主项目6 agent,较久)。稍后侧栏『刷新』。");
    try { await fetch(`/api/books/${encodeURIComponent(slug)}/base`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }); }
    catch (e: any) { setMsg("启动失败: " + e.message); }
  }
  if (!world.length && !fore.length && !plot.length) return (
    <div className="card">
      <h2>设定 · 伏笔 · 剧情点</h2>
      <div className="muted" style={{ marginBottom: 10 }}>还没有基础抽取数据 — 复用主项目的实体/伏笔/剧情/世界规则抽取。</div>
      <button className="btn" onClick={run}>运行基础抽取</button>
      {msg && <div className="muted" style={{ marginTop: 10, fontSize: 13 }}>{msg}</div>}
    </div>
  );
  return (
    <>
      {!!world.length && <div className="card">
        <h2>世界设定词条 <span className="tag">{world.length} 条 · 出现章序</span></h2>
        <div className="tablescroll"><table>
          <thead><tr><th>词条</th><th>释义</th><th>首现</th></tr></thead>
          <tbody>{world.map((w: any, i: number) => (
            <tr key={i}><td><b>{w.term}</b></td><td className="muted">{w.definition}</td><td>{w.first_chapter}</td></tr>
          ))}</tbody></table></div>
      </div>}
      {!!fore.length && <div className="card">
        <h2>伏笔 <span className="tag">{fore.length} 条 · 埋设→回收</span></h2>
        <div className="tablescroll"><table>
          <thead><tr><th>埋设章</th><th>回收章</th><th>状态</th><th>类型</th><th>描述</th></tr></thead>
          <tbody>{fore.map((f: any, i: number) => (
            <tr key={i}><td>{f.planted_chapter}</td>
              <td>{f.resolved_chapter || <span className="pill dump">未回收</span>}</td>
              <td>{f.status}</td><td className="muted">{f.type}</td><td className="muted">{f.description}</td></tr>
          ))}</tbody></table></div>
      </div>}
      {!!plot.length && <div className="card">
        <h2>剧情点 <span className="tag">{plot.length} 条 · 按章</span></h2>
        <div className="tablescroll"><table>
          <thead><tr><th>章</th><th>重要度</th><th>剧情</th></tr></thead>
          <tbody>{plot.map((p: any, i: number) => (
            <tr key={i}><td>{p.chapter}</td><td>{p.importance}</td><td className="muted">{p.summary}</td></tr>
          ))}</tbody></table></div>
      </div>}
    </>
  );
}

function Empty({ layer }: { layer: string }) {
  return <div className="card"><div className="empty">暂无「{layer}」数据 — 点上方『运行分析』后刷新</div></div>;
}
