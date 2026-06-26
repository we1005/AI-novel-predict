"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import Icon from "@/components/Icon";
import Link from "next/link";
import Chart from "@/components/Chart";

const SCENE_COLORS: Record<string, string> = {
  铺垫: "#9a6b2f", 小高潮: "#cf6b4a", 大高潮: "#c0392b", 热血: "#c8552f",
  悬疑惊悚: "#565a8c", 煽情: "#2e6f80", 日常: "#8a8270", 转场: "#b3a98f",
  其他: "#a0957c", 信息揭示: "#7a8a6a",
};

// L1 词汇密度热力条:层(行)× 场景(列),色深∝每千字密度
function DensityHeat({ data }: { data: Record<string, Record<string, number>> }) {
  const layers = Object.keys(data);
  if (!layers.length) return null;
  const scenes = Array.from(new Set(layers.flatMap((l) => Object.keys(data[l] || {}))));
  let max = 0;
  layers.forEach((l) => scenes.forEach((s) => { max = Math.max(max, data[l]?.[s] || 0); }));
  max = max || 1;
  const cell = (v: number) => ({
    background: `rgba(192,57,43,${(v / max) * 0.85 + (v ? 0.06 : 0)})`,
    color: v / max > 0.5 ? "#fdf6f2" : "var(--ink-dim)",
  });
  return (
    <div style={{ overflowX: "auto", marginBottom: 12 }}>
      <table style={{ borderCollapse: "separate", borderSpacing: 2, fontSize: 11 }}>
        <thead><tr><th style={{ textAlign: "right", padding: "2px 6px", color: "var(--muted)", fontFamily: "var(--mono)" }}>层 \ 场景</th>
          {scenes.map((s) => <th key={s} style={{ padding: "2px 4px", color: "var(--zhe)", fontFamily: "var(--mono)", fontWeight: 500, whiteSpace: "nowrap" }}>{s}</th>)}
        </tr></thead>
        <tbody>{layers.map((l) => (
          <tr key={l}>
            <td style={{ textAlign: "right", padding: "2px 6px", color: "var(--ink)", whiteSpace: "nowrap", fontFamily: "var(--mono)" }}>{l}</td>
            {scenes.map((s) => { const v = data[l]?.[s] || 0; return (
              <td key={s} title={`${l} · ${s}: ${v}/千字`} style={{ ...cell(v), textAlign: "center", padding: "4px 6px", borderRadius: 2, minWidth: 34 }}>{v || ""}</td>
            ); })}
          </tr>
        ))}</tbody>
      </table>
      <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>色深 ∝ 该层词在该场景的每千字密度;空白=≈0。可见各语义场在不同场景的浓度差异(如不可名状词在大高潮最浓)。</div>
    </div>
  );
}

// L7 场景转移图:有向图,边宽/不透明度 ∝ 转移概率(环路安全)
function TransitionGraph({ data }: { data: Record<string, Record<string, number>> }) {
  const froms = Object.keys(data || {});
  if (!froms.length) return null;
  const nodeSet = new Set<string>(froms);
  froms.forEach((a) => Object.keys(data[a] || {}).forEach((b) => nodeSet.add(b)));
  const nodes = Array.from(nodeSet).map((n) => ({ name: n, itemStyle: { color: SCENE_COLORS[n] || "#8a8270" }, symbolSize: 30 }));
  const links: any[] = [];
  froms.forEach((a) => Object.entries(data[a] || {}).forEach(([b, p]) => {
    if ((p as number) >= 0.12) links.push({
      source: a, target: b, value: p,
      lineStyle: { width: 1 + (p as number) * 7, opacity: 0.35 + (p as number) * 0.55, curveness: 0.22, color: SCENE_COLORS[a] || "#999" },
    });
  }));
  const option = {
    tooltip: { formatter: (x: any) => x.dataType === "edge" ? `${x.data.source} → ${x.data.target}<br/>转移概率 ${(x.data.value * 100).toFixed(0)}%` : x.name },
    series: [{
      type: "graph", layout: "circular", circular: { rotateLabel: true },
      roam: true, label: { show: true, color: "#211d16", fontFamily: "-apple-system,'PingFang SC',sans-serif" },
      edgeSymbol: ["none", "arrow"], edgeSymbolSize: 7,
      data: nodes, links, lineStyle: { curveness: 0.2 },
    }],
  };
  return (
    <div style={{ marginBottom: 12 }}>
      <Chart option={option} height={380} />
      <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>节点=场景类型,有向边=该作者"上一拍→下一拍"的转移倾向(边越粗概率越高,仅显示≥12%)。可当采样器逐章驱动生成。</div>
    </div>
  );
}

// 七层「阐释」内容(怎么实现) + 对应 live 数据键
const LAYERS = [
  { id: "L1", key: "lexicon", t: "词汇分层", cap: "用词调色盘:每层词在什么场景该撒多浓",
    sample: "按 scene_type 分桶,每桶取张力最高的代表章原文。",
    how: "LLM 把实词归入语义场(克苏鲁不可名状 / 蒸汽朋克器物 / 宗教 / 感官身体 / 军事…),只收原文真出现的词 + 逐字共现搭配,不许编造。",
    code: "每层词在每个场景桶里 str.count / 千字 → density_by_scene。LLM 估值不准,就用纯代码量化兜底。",
    out: "strata:[{layer, signature_words, collocations, trigger_context}], diction, avoid",
    spec: "渲染成「用词调色盘」:每层标志词 + 该类场景的密度配比。" },
  { id: "L2", key: "syntax", t: "句式构式", cap: "可填空的句式骨架库,不是一句话节奏总结",
    sample: "按 scene_type × plot_function 分桶;直接复用 craft 26 类已切好的逐字片段(省 token、保证逐字)。",
    how: "LLM 抽反复使用的句式构造,抽象成带槽模板(如『随着[X],[Y]』),给触发场景 / 效果 / 逐字例句。",
    code: "弱断言(似乎 / 仿佛)用正则全书计数得真实频率;LLM 只判定『滥用红线』倍数 → 防网文腔。",
    out: "templates:[{skeleton, trigger_scenes, freq_band, exemplars, misuse_redline}], hedge_usage, rhythm",
    spec: "「句式骨架库」:填空模板 + 频率上限 + 滥用红线。" },
  { id: "L3", key: "rhetoric", t: "修辞 · 叙述声音", cap: "比喻怎么打 + 叙述者站多近、是否议论",
    sample: "煽情 / 悬疑 / 人物刻画桶权重高;复用 craft 的 signature_metaphor / interior / monologue 片段。",
    how: "LLM 逐条记比喻 [本体]→[喻体] 归语义场;分析叙述距离、自由间接引语(FID)、旁白评议、心理动词、反问设问。",
    code: "叠词、省略号独段用正则全书计数补强。",
    out: "metaphor_map{favored, vehicle_dist}, reduplications, narrator{distance, fid_examples, psych_verbs}",
    spec: "「修辞与叙述者操作手册」:喻体取向 + FID / 叙述距离 + 招牌一招。" },
  { id: "L4", key: "atmosphere", t: "类型氛围配方", cap: "蒸汽朋克 / 克苏鲁到底靠什么手段营造",
    sample: "高氛围取样:scene_type∈{悬疑惊悚, 大高潮} 且张力≥70 + 世界观揭示命中超自然概念的章。",
    how: "分类型拆 carrier:means(回避命名 / 感官失序 / 理智代价 / 器物密度 / 能源-机械隐喻…)→ how → 逐字例证,并给黄金律。",
    code: "carrier 词在对应场景桶 str.count / 千字 → 剂量。",
    out: "genres:[{genre, techniques:[{means, how, intensity, examples, density}], golden_rule, lexicon{do, avoid}}]",
    spec: "每质感一张「配方卡」+ 黄金律(如克苏鲁:永不正面写本体,只写反应与代价)。" },
  { id: "L5", key: "scene_routine", t: "场景调度套路", cap: "写某类场面的『分场拍摄剧本』(最补缺陷的一层)",
    sample: "每类 scene_type 取整场全文(不截断)6-10 场,优先高潮 / 强钩子章——顺序是命门。",
    how: "LLM 逆向写作程序:从哪切入(机位枚举)→ 节拍数组(每拍 function + 镜头 + 字数占比)→ 详略五分类% → POV 距离 → 收尾钩子模板。",
    code: "聚合:opening_cut 算分布、beat_function 序列做 bigram 转移、详略 / 字数占比求均。",
    out: "routines:[{scene_type, opening_cut{dist}, modal_beat_sequence, detail_budget, exit{hook_grammar, hook_template}}]",
    spec: "「分场景调度手册」:每类场面 切入 → 节拍链 → 详略 → 钩子模板。" },
  { id: "L6", key: "macro_arch", t: "宏观架构", cap: "片段法抓不到的整体结构(关系 / 序列 / 转移)",
    sample: "大部分纯代码:复用既有 foreshadowing 表 + chapter_beat 全序列 + pov_event + 速读阶段。",
    how: "伏笔账本(plant→payoff 跨度 / 长线比)、信息预算(逐章载体 / drip 序列)、章型模板由 LLM 切 macro-block 序列再聚类。",
    code: "张力控制律(峰检测 / 上升斜率 / 回落 / 峰间距分位)、POV 调度、伏笔跨度统计 全为纯代码。",
    out: "foreshadow{threads, stats}, info_budget, tension_law, pov_schedule, chapter_type_templates",
    spec: "「宏观编排纪律」:伏笔中位跨度 / 反信息倾倒红线 / 张力控制律 / POV 调度规则。" },
  { id: "L7", key: "transition", t: "转移模型", cap: "状态→下一步倾向(Transformer / LSTM 类比)",
    sample: "纯代码:chapter_beat 的 scene_type / plot_function 序列。",
    how: "对相邻状态计数 → 归一成转移概率,得一阶(可扩二阶)马尔可夫矩阵 + 每状态最可能的下一拍。",
    code: "全为确定性矩阵计算,零 LLM。",
    out: "scene_transition{a:{b:prob}}, plot_function_transition, most_likely_next",
    spec: "「场景递进倾向表」:上一拍 → 最可能的下一拍,可当采样器逐章驱动。" },
];

function Rail() {
  return (
    <aside className="rail">
      <Link href="/" className="railbrand"><span className="railseal">墨</span><span>墨析</span></Link>
      <nav className="railnav">
        <Link href="/" className="railitem"><Icon k="analyze" /><span>深度分析</span></Link>
        <Link href="/generate" className="railitem"><Icon k="compose" /><span>仿写 · 重组</span></Link>
        <Link href="/architecture" className="railitem"><Icon k="arch" /><span>架构</span></Link>
      </nav>
      <div className="railsection">专页</div>
      <div className="railitem active"><Icon k="style" /><span>文风基因组</span></div>
    </aside>
  );
}

export default function GenomeDoc() {
  const [books, setBooks] = useState<any[]>([]);
  const [slug, setSlug] = useState("");
  const [g, setG] = useState<any>(null);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    api.books().then((bs) => {
      setBooks(bs);
      const f = bs.find((b: any) => b.analyzed) || bs[0];
      if (f) setSlug(f.slug);
    }).catch((e) => setMsg("无法连接后端 — " + e.message));
  }, []);
  useEffect(() => {
    if (!slug) return;
    fetch(`/api/books/${encodeURIComponent(slug)}/genome`).then((r) => r.json())
      .then(setG).catch(() => setG(null));
  }, [slug]);

  const present: string[] = g?.layers_present || [];
  const genome = g?.genome || {};
  const trim = (v: any) => { const s = JSON.stringify(v, null, 2); return s && s.length > 1400 ? s.slice(0, 1400) + "\n… (截断)" : s; };

  return (
    <div className="applayout">
      <Rail />
      <main className="appmain">
        <span className="eyebrow">STYLE GENOME · DEEP DIVE</span>
        <div className="h1">文风基因组 · 七层详解</div>
        <div className="sub">不是一段文风总结,而是<b>可复用、可喂给别的 LLM 复现</b>的分层范式。下面逐层讲清它<b>怎么实现</b>,并用真实抽取数据<b>展示</b>。</div>

        <div className="card">
          <select value={slug} onChange={(e) => setSlug(e.target.value)} style={{ maxWidth: 360 }}>
            {books.map((b) => <option key={b.slug} value={b.slug}>{b.analyzed ? "● " : "○ "}{b.title || b.slug}</option>)}
          </select>
          {msg && <div className="muted" style={{ marginTop: 8, fontSize: 13 }}>{msg}</div>}
          {!present.length && <div className="muted" style={{ marginTop: 8, fontSize: 13 }}>该书还没抽取基因组——到「深度分析 → 文风基因组」Tab 点『抽取』。下面仍可看实现原理。</div>}
        </div>

        <div className="card">
          <span className="eyebrow">CORE IDEA</span>
          <h2>核心思路</h2>
          <p style={{ fontSize: 14, lineHeight: 1.85, color: "var(--ink)", margin: "0 0 6px" }}>
            基线方法把整本书的文风浓缩成一段话喂给模型,信息太薄、且<b>全程一个腔</b>。基因组的破解是两条:
          </p>
          <p style={{ fontSize: 13.5, lineHeight: 1.8, color: "var(--ink-dim)", margin: 0 }}>
            ① <b>定性范式一律挂上频率 / 密度</b>(用代码量化兜底,不让 LLM 估值漂移);
            ② <b>按场景类型路由</b>——打斗场和日常场的用词浓度 / 句式 / 调度本就不同,所以把"风格"从一个全局常量,
            升级成<b>可路由的状态机</b>。每层都走「分桶取样 → LLM 抽范式 → 纯代码量化 → 落结构化 JSON」,
            最后组装成<b>可计算指纹</b> + <b>可直接当 system-prompt 的 spec</b>。
          </p>
          <div className="pipe" style={{ marginTop: 14 }}>
            <div className="pb k1"><b>分桶取样</b>scene_type×POV<br/>整场不截断</div>
            <div className="pa">→</div>
            <div className="pb k2"><b>逐层抽取</b>LLM 抽范式<br/>+ 代码量化兜底</div>
            <div className="pa">→</div>
            <div className="pb k2"><b>组装</b>7 层卡<br/>+ 指纹向量</div>
            <div className="pa">→</div>
            <div className="pb k3"><b>双档渲染</b>静态 spec /<br/>动态逐章 brief</div>
            <div className="pa">→</div>
            <div className="pb k3"><b>驱动 writer</b>seed_genome<br/>仿写</div>
            <div className="pa">→</div>
            <div className="pb k3"><b>对账回灌</b>同 schema 扫产出<br/>→ 指纹 diff → 修 spec</div>
          </div>
        </div>

        {LAYERS.map((L) => {
          const live = genome[L.key];
          const got = present.includes(L.key);
          return (
            <div key={L.id} className="card">
              <div className="ghead" style={{ marginBottom: 12 }}>
                <span className="gid" style={{ fontSize: 14 }}>{L.id}</span>
                <span className="gt" style={{ fontSize: 18 }}>{L.t}</span>
                <span className="gcap">{L.cap}</span>
              </div>
              <div className="gsub" style={{ marginBottom: live ? 14 : 0 }}>
                <span className="gk">取样</span><span className="gv">{L.sample}</span>
                <span className="gk">LLM抽</span><span className="gv">{L.how}</span>
                <span className="gk">代码兜底</span><span className="gv">{L.code}</span>
                <span className="gk">输出</span><span className="gv"><code>{L.out}</code></span>
                <span className="gk">进spec</span><span className="gv">{L.spec}</span>
              </div>
              {got && live && (
                <div>
                  <div className="eyebrow" style={{ marginBottom: 6 }}>本书实抽样例 · {slug}</div>
                  {L.key === "lexicon" && live.density_by_scene && <DensityHeat data={live.density_by_scene} />}
                  {L.key === "transition" && live.scene_transition && <TransitionGraph data={live.scene_transition} />}
                  <div className="tablescroll" style={{ maxHeight: 300, padding: "10px 12px" }}>
                    <pre style={{ whiteSpace: "pre-wrap", margin: 0, fontSize: 11.8, lineHeight: 1.6, fontFamily: "var(--mono)" }}>{trim(live)}</pre>
                  </div>
                </div>
              )}
            </div>
          );
        })}

        <div className="card">
          <span className="eyebrow">REUSE</span>
          <h2>两档复用 · 从分析产物到生成驱动</h2>
          <div className="archlayer">
            <div className="archrow"><span className="t">静态档(软用)</span><span className="d">把渲染出的 spec 直接拼进 writer 的 system prompt(compose.seed_genome),零改生成链即生效。</span></div>
            <div className="archrow"><span className="t">动态档(硬用)</span><span className="d">把 L7 转移矩阵当采样器:逐章给定当前状态 → 采样下一拍 scene_type / 张力 / POV → 取该场景 L5 调度卡 + L6 章型模板 + 待办伏笔栈 → 组装成"本章导演 brief"再交 writer 填词。这就是"可运行的状态机"。</span></div>
          </div>
        </div>

        <div className="card">
          <span className="eyebrow">VERIFIED</span>
          <h2>效果:对照基线的 7 维盲评</h2>
          <p style={{ fontSize: 13.5, lineHeight: 1.8, margin: 0, color: "var(--ink)" }}>
            同一章大纲,基线(单段总结)与基因组(分层 spec)各生成一章,以原著真实片段为标尺做 7 维盲评:
            <b>基因组全面胜出</b>——词汇 / 句式 / 修辞 / 氛围 / 场景调度 / 钩子 / 整体 七维全部领先,
            整体 65.25 vs 56.75、场景调度 +10.75,4 场赢 3。详见「架构 → ⑤ 评测闭环」。
          </p>
        </div>
      </main>
    </div>
  );
}
