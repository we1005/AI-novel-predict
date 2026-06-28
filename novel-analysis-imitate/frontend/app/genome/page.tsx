"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import Icon from "@/components/Icon";
import Link from "next/link";
import Chart from "@/components/Chart";
import { M, MB } from "@/components/Math";

const SCENE_COLORS: Record<string, string> = {
  铺垫: "#9a6b2f", 小高潮: "#cf6b4a", 大高潮: "#c0392b", 热血: "#c8552f",
  悬疑惊悚: "#565a8c", 煽情: "#2e6f80", 日常: "#8a8270", 转场: "#b3a98f",
  其他: "#a0957c", 信息揭示: "#7a8a6a",
};

type Layer = {
  id: string; key: string; t: string; cap: string;
  sample: string; how: string; code: string; out: string; spec: string;
  nanny: string; formula?: string; formulaNote?: string; example?: string;
};

const LAYERS: Layer[] = [
  {
    id: "L1", key: "lexicon", t: "词汇分层", cap: `用词调色盘:每层词在什么场景该撒多浓`,
    nanny: `先把作者爱用的实词按「语义场」分成几摞(克苏鲁不可名状词、蒸汽朋克器物词、宗教词…),再算每一摞词在不同场景里的浓度——同样是「血」,打斗场撒得多、日常场几乎不撒。这样模型就知道:写大高潮该往哪类词上堆,写日常该收敛。`,
    formula: String.raw`\rho_{\ell,s}=\frac{\displaystyle\sum_{w\in W_\ell}\operatorname{count}_s(w)}{N_s}\times 1000`,
    formulaNote: `ρ=层 ℓ 在场景 s 的每千字密度;Wₗ=该层词表;count_s(w)=词 w 在该场景所有章里出现次数;N_s=该场景总字数。`,
    example: `不可名状层在「大高潮」桶里词共出现 ~615 次、该桶约 10 万字 → ρ≈6.15/千字;同层在「日常」桶仅 2.05。差三倍,这就是分场景配比。`,
    sample: `按 scene_type 分桶,每桶取张力最高的代表章原文。`,
    how: `LLM 把实词归入语义场,只收原文真出现的词 + 逐字共现搭配,不许编造。`,
    code: `每层词在每个场景桶里 str.count/千字 → density_by_scene,LLM 估值不准就用纯代码量化兜底。`,
    out: `strata:[{layer, signature_words, collocations, trigger_context}], diction, avoid`,
    spec: `渲染成「用词调色盘」:每层标志词 + 该类场景的密度配比。`,
  },
  {
    id: "L2", key: "syntax", t: "句式构式", cap: `可填空的句式骨架库 + 滥用红线`,
    nanny: `作者反复用的句子结构(比如「随着[X],[Y]」这种渐进恐怖长句),抽象成带空格的模板,模型照着填就行。同时给弱断言词(似乎/仿佛)设一条频率红线——用太多就是网文腔,用代码量出原作的真实频率当上限。`,
    formula: String.raw`r_{\text{hedge}}=\frac{|\{\,似乎,\,仿佛,\,如同,\,宛如\,\}|}{N}\times 1000,\quad \text{红线}=k\cdot r_{\text{hedge}}`,
    formulaNote: `r=原作弱断言每千字频率(正则全书计数 / 总字数);红线=k 倍均值(k≈3),生成稿超了即判网文腔。`,
    sample: `按 scene_type × plot_function 分桶;复用 craft 26 类已切好的逐字片段。`,
    how: `LLM 抽反复使用的句式构造,抽象成带槽模板,给触发场景/效果/逐字例句。`,
    code: `弱断言用正则全书计数得真实频率;LLM 只判定滥用红线倍数。`,
    out: `templates:[{skeleton, trigger_scenes, freq_band, exemplars, misuse_redline}], hedge_usage, rhythm`,
    spec: `「句式骨架库」:填空模板 + 频率上限 + 滥用红线。`,
  },
  {
    id: "L3", key: "rhetoric", t: "修辞 · 叙述声音", cap: `比喻怎么打 + 叙述者站多近、是否议论`,
    nanny: `两件事:① 比喻偏好——作者爱把「人」比作什么?把「声音」比作什么?统计本体→喻体的映射方向;② 叙述声音——镜头是贴着人物内心(自由间接引语 FID),还是跳出来发议论?爱用哪些心理动词(觉得/不禁/迟疑)?这些决定了读起来像不像同一个讲故事的人。`,
    sample: `煽情/悬疑/人物刻画桶权重高;复用 craft 的 signature_metaphor/interior/monologue 片段。`,
    how: `LLM 逐条记比喻 [本体]→[喻体] 归语义场;分析叙述距离/FID/旁白评议/心理动词/反问。`,
    code: `叠词、省略号独段用正则全书计数补强。`,
    out: `metaphor_map{favored, vehicle_dist}, reduplications, narrator{distance, fid_examples, psych_verbs}`,
    spec: `「修辞与叙述者操作手册」:喻体取向 + FID/距离 + 招牌一招。`,
  },
  {
    id: "L4", key: "atmosphere", t: "类型氛围配方", cap: `蒸汽朋克/克苏鲁到底靠什么手段营造`,
    nanny: `把「质感」拆成可照做的配方表:克苏鲁的恐怖不是写出怪物长相,而是靠「回避命名 + 感官失序 + 理智代价」;蒸汽朋克靠「器物密度 + 能源-机械隐喻 + 阶级对照」。每条手段配一句怎么做 + 原文例证 + 剂量,并给一条黄金律(如:永不正面写本体,只写反应)。`,
    formulaNote: `每条 carrier 的剂量同样用密度公式 ρ 量化(见 L1),让氛围配方也带可调旋钮。`,
    sample: `高氛围取样:悬疑/大高潮且张力≥70 + 世界观揭示命中超自然概念的章。`,
    how: `分类型拆 carrier:means→how→逐字例证,给黄金律。`,
    code: `carrier 词在对应场景桶 str.count/千字 → 剂量。`,
    out: `genres:[{genre, techniques:[{means, how, intensity, examples, density}], golden_rule, lexicon{do, avoid}}]`,
    spec: `每质感一张「配方卡」+ 黄金律。`,
  },
  {
    id: "L5", key: "scene_routine", t: "场景调度套路", cap: `写某类场面的『分场拍摄剧本』`,
    nanny: `这是片段法最抓不到、却最关键的:作者写一场打斗,是先写景、先对话、还是直接动作?(切入机位)然后按什么节拍推进(对峙→升级→爆发→代价)?哪段详写哪段快切?怎么收尾留钩子?把每类场景逆向成一份分镜剧本,新写一场同类戏就照这个骨架走。`,
    formula: String.raw`P_{\text{cut}}(c\mid s)=\frac{\#\{\text{场景 }s\text{ 以 }c\text{ 切入}\}}{\#\{\text{场景 }s\}},\quad T(b'\mid b)=\frac{\operatorname{count}(b\to b')}{\sum_{b''}\operatorname{count}(b\to b'')}`,
    formulaNote: `P_cut=某类场景从机位 c(景物/对话/动作…)切入的概率分布;T=节拍 b→b' 的 bigram 转移(节拍序列也是个小马尔可夫链)。`,
    sample: `每类 scene_type 取整场全文(不截断)6-10 场,顺序是命门。`,
    how: `LLM 逆向写作程序:切入机位→节拍数组(每拍 function+镜头+字数占比)→详略五分类%→POV→收尾钩子模板。`,
    code: `聚合:opening_cut 算分布、beat_function 序列做 bigram 转移、详略求均。`,
    out: `routines:[{scene_type, opening_cut{dist}, modal_beat_sequence, detail_budget, exit{hook_grammar, hook_template}}]`,
    spec: `「分场景调度手册」:每类场面 切入→节拍链→详略→钩子模板。`,
  },
  {
    id: "L6", key: "macro_arch", t: "宏观架构", cap: `伏笔/张力/POV 的整本结构`,
    nanny: `整本书的骨架:伏笔埋下后隔多远才回收(长线还是短线)?张力曲线怎么起伏、隔几章来一个大高潮?什么时候离开主角视角、离开多久?这些是逐章片段拼不出来的全局规律,大多直接用代码从已抽好的伏笔表/节拍序列里算出来。`,
    formula: String.raw`\bar g=\frac{1}{k-1}\sum_{i=1}^{k-1}(p_{i+1}-p_i),\qquad \text{峰}=\{\,t: \tau_t\ge 80\ \wedge\ \tau_t\ge\tau_{t\pm1}\,\}`,
    formulaNote: `p_i=第 i 个高潮所在章号,ḡ=大高潮平均间距;τ_t=第 t 章张力,局部极大且≥80 即判定为峰。伏笔跨度=回收章−埋设章,取中位数。`,
    example: `余烬之铳:794 条伏笔,中位跨度 95 章、47% 是百章以上长线 → 量化坐实「慢热长线悬疑」。`,
    sample: `大部分纯代码:复用既有 foreshadowing 表 + chapter_beat 全序列 + pov_event + 速读阶段。`,
    how: `伏笔账本、信息预算由代码聚合;章型模板由 LLM 切 macro-block 序列再聚类。`,
    code: `张力控制律(峰检测/斜率/回落/峰间距分位)、POV调度、伏笔跨度统计全为纯代码。`,
    out: `foreshadow{threads, stats}, info_budget, tension_law, pov_schedule, chapter_type_templates`,
    spec: `「宏观编排纪律」:伏笔中位跨度/反信息倾倒红线/张力控制律/POV调度规则。`,
  },
  {
    id: "L7", key: "transition", t: "转移模型", cap: `状态→下一步倾向(Transformer/LSTM 类比)`,
    nanny: `把全书每章的「场景类型」连成一条序列(铺垫→小高潮→悬疑→大高潮→喘息…),统计「上一拍是 A 时、下一拍是 B」的概率。这就得到一张转移概率表——本质是一个一阶马尔可夫链,正对应你说的「像 LSTM/Transformer 那样的状态转移」。生成时它能当采样器:当前在铺垫,就按概率挑下一拍最可能是什么。`,
    formula: String.raw`P(s_{t+1}=b \mid s_t=a)=\frac{\operatorname{count}(a\to b)}{\displaystyle\sum_{b'}\operatorname{count}(a\to b')}`,
    formulaNote: `s_t=第 t 章场景类型;count(a→b)=全书中「a 之后紧跟 b」的次数;分母归一,使每行概率和为 1。`,
    example: `若「大高潮」后 55% 接「喘息/转场」、30% 接「小高潮」 → 模型在写完大高潮后,会优先安排一段回落,而不是连续炸。`,
    sample: `纯代码:chapter_beat 的 scene_type / plot_function 序列。`,
    how: `对相邻状态计数 → 归一成转移概率,得一阶(可扩二阶)马尔可夫矩阵 + 每状态最可能的下一拍。`,
    code: `全为确定性矩阵计算,零 LLM。`,
    out: `scene_transition{a:{b:prob}}, plot_function_transition, most_likely_next`,
    spec: `「场景递进倾向表」:上一拍→最可能的下一拍,可当采样器逐章驱动。`,
  },
];

function Rail() {
  return (
    <aside className="rail">
      <Link href="/" className="railbrand"><span className="railseal">墨</span><span>墨析</span></Link>
      <nav className="railnav">
        <Link href="/" className="railitem"><Icon k="analyze" /><span>深度分析</span></Link>
        <Link href="/generate" className="railitem"><Icon k="compose" /><span>仿写 · 重组</span></Link>
        <Link href="/genre" className="railitem"><Icon k="style" /><span>类型模板</span></Link>
        <Link href="/architecture" className="railitem"><Icon k="arch" /><span>架构</span></Link>
      </nav>
      <div className="railsection">专页</div>
      <div className="railitem active"><Icon k="style" /><span>文风基因组</span></div>
    </aside>
  );
}

function DensityHeat({ data }: { data: Record<string, Record<string, number>> }) {
  const layers = Object.keys(data);
  if (!layers.length) return null;
  const scenes = Array.from(new Set(layers.flatMap((l) => Object.keys(data[l] || {}))));
  let max = 0;
  layers.forEach((l) => scenes.forEach((s) => { max = Math.max(max, data[l]?.[s] || 0); }));
  max = max || 1;
  const cell = (v: number) => ({ background: `rgba(192,57,43,${(v / max) * 0.85 + (v ? 0.06 : 0)})`, color: v / max > 0.5 ? "#fdf6f2" : "var(--ink-dim)" });
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
      <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>色深 ∝ 每千字密度;空白≈0。</div>
    </div>
  );
}

function TransitionGraph({ data }: { data: Record<string, Record<string, number>> }) {
  const froms = Object.keys(data || {});
  if (!froms.length) return null;
  const nodeSet = new Set<string>(froms);
  froms.forEach((a) => Object.keys(data[a] || {}).forEach((b) => nodeSet.add(b)));
  const nodes = Array.from(nodeSet).map((n) => ({ name: n, itemStyle: { color: SCENE_COLORS[n] || "#8a8270" }, symbolSize: 30 }));
  const links: any[] = [];
  froms.forEach((a) => Object.entries(data[a] || {}).forEach(([b, p]) => {
    if ((p as number) >= 0.12) links.push({ source: a, target: b, value: p, lineStyle: { width: 1 + (p as number) * 7, opacity: 0.35 + (p as number) * 0.55, curveness: 0.22, color: SCENE_COLORS[a] || "#999" } });
  }));
  const option = {
    tooltip: { formatter: (x: any) => x.dataType === "edge" ? `${x.data.source} → ${x.data.target}<br/>转移概率 ${(x.data.value * 100).toFixed(0)}%` : x.name },
    series: [{ type: "graph", layout: "circular", circular: { rotateLabel: true }, roam: true, label: { show: true, color: "#211d16", fontFamily: "-apple-system,'PingFang SC',sans-serif" }, edgeSymbol: ["none", "arrow"], edgeSymbolSize: 7, data: nodes, links, lineStyle: { curveness: 0.2 } }],
  };
  return (
    <div style={{ marginBottom: 12 }}>
      <Chart option={option} height={380} />
      <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>有向边=上一拍→下一拍的转移倾向(边越粗概率越高,仅显示≥12%)。</div>
    </div>
  );
}

export default function GenomeDoc() {
  const [books, setBooks] = useState<any[]>([]);
  const [slug, setSlug] = useState("");
  const [g, setG] = useState<any>(null);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    api.books().then((bs) => { setBooks(bs); const f = bs.find((b: any) => b.analyzed) || bs[0]; if (f) setSlug(f.slug); })
      .catch((e) => setMsg("无法连接后端 — " + e.message));
  }, []);
  useEffect(() => {
    if (!slug) return;
    fetch(`/api/books/${encodeURIComponent(slug)}/genome`).then((r) => r.json()).then(setG).catch(() => setG(null));
  }, [slug]);

  const present: string[] = g?.layers_present || [];
  const genome = g?.genome || {};
  const trim = (v: any) => { const s = JSON.stringify(v, null, 2); return s && s.length > 1400 ? s.slice(0, 1400) + "\n… (截断)" : s; };

  return (
    <div className="applayout">
      <Rail />
      <main className="appmain">
        <span className="eyebrow">STYLE GENOME · 保姆级详解</span>
        <div className="h1">文风基因组 · 七层详解</div>
        <div className="sub">不是一段文风总结,而是<b>可复用、可喂给别的 LLM 复现</b>的分层范式。下面从直觉、公式到真实数据,逐层讲透它<b>怎么实现</b>。</div>

        <div className="card">
          <select value={slug} onChange={(e) => setSlug(e.target.value)} style={{ maxWidth: 360 }}>
            {books.map((b) => <option key={b.slug} value={b.slug}>{b.analyzed ? "● " : "○ "}{b.title || b.slug}</option>)}
          </select>
          {msg && <div className="muted" style={{ marginTop: 8, fontSize: 13 }}>{msg}</div>}
          {!present.length && <div className="muted" style={{ marginTop: 8, fontSize: 13 }}>该书还没抽取基因组——到「深度分析 → 文风基因组」点『抽取』。下面仍可看实现原理。</div>}
        </div>

        {/* 一句话直觉 */}
        <div className="card doc">
          <span className="eyebrow">先用一句话理解</span>
          <h2 style={{ marginTop: 4 }}>它到底在干嘛?</h2>
          <p>想象你要让一个枪手模仿某位作家。给他一句"文笔冷硬、画面感强"——他写出来四不像。<b>文风基因组</b>做的是把这位作家的笔法拆成<b>七本可执行的手册</b>:用哪些词、什么场景用多浓(L1)、爱用什么句式(L2)、怎么打比喻/站多近(L3)、靠什么营造类型质感(L4)、每类场面怎么分镜(L5)、整本怎么埋伏笔控张力(L6)、一拍接一拍的习惯(L7)。</p>
          <div className="callout"><span className="lab">关键设计</span>① 所有定性范式都<b>挂上频率/密度</b>(用代码量化,不让模型瞎估);② 所有参数<b>按场景路由</b>——把"风格"从一个全局常量,升级成一台<b>可路由的状态机</b>,根治"全程一个腔"。</div>
          <div className="pipe">
            <div className="pb k1"><b>分桶取样</b>scene×POV<br/>整场不截断</div><div className="pa">→</div>
            <div className="pb k2"><b>逐层抽取</b>LLM抽范式<br/>+代码量化</div><div className="pa">→</div>
            <div className="pb k2"><b>组装</b>7层卡<br/>+指纹向量</div><div className="pa">→</div>
            <div className="pb k3"><b>双档渲染</b>静态spec/<br/>动态brief</div><div className="pa">→</div>
            <div className="pb k3"><b>驱动writer</b>seed_genome</div><div className="pa">→</div>
            <div className="pb k3"><b>对账回灌</b>指纹diff→修spec</div>
          </div>
        </div>

        {/* 数学基础 */}
        <div className="card doc">
          <span className="eyebrow">MATH</span>
          <h2 style={{ marginTop: 4 }}>把"文风"变成数字 · 三族公式</h2>
          <p>整套基因组的可计算性,落在三类简单公式上。看懂这三条,后面每层的"代码兜底"就都通了。</p>
          <h3>① 密度(浓度):衡量"某类词撒多浓"</h3>
          <MB>{String.raw`\rho=\frac{\text{命中次数}}{\text{文本字数}}\times 1000\quad(\text{每千字次数})`}</MB>
          <p className="formula-note">L1 词汇、L4 题材剂量、L2 弱断言频率,全是这一条的变体——纯字符串计数,零模型估值。</p>
          <h3>② 转移概率:衡量"一拍接一拍的习惯"</h3>
          <MB>{String.raw`P(b\mid a)=\frac{\operatorname{count}(a\to b)}{\sum_{b'}\operatorname{count}(a\to b')}`}</MB>
          <p className="formula-note">L7 场景转移、L5 节拍 bigram,都是这条——一阶马尔可夫链,即"Transformer/LSTM 类比"里的状态转移。</p>
          <h3>③ 保真度:衡量"生成稿像不像原著"</h3>
          <p>用同一套抽取把生成稿也压成指纹向量,再与原著逐维比。分布维用余弦相似、标量维用相对误差:</p>
          <MB>{String.raw`\cos(\mathbf u,\mathbf v)=\frac{\mathbf u\cdot\mathbf v}{\lVert\mathbf u\rVert\,\lVert\mathbf v\rVert},\qquad \text{Fidelity}=100\Big(1-\frac1n\sum_{i}\text{penalty}_i\Big)`}</MB>
          <p className="formula-note">(可选)分布也可用 KL 散度 <M>{String.raw`D_{\mathrm{KL}}(P\Vert Q)=\sum_i p_i\log\frac{p_i}{q_i}`}</M>。这把"像不像"从人工感觉变成<b>可计算的目标函数</b>,正是评测对账的底座。</p>
        </div>

        {/* 逐层 */}
        {LAYERS.map((L) => {
          const live = genome[L.key];
          const got = present.includes(L.key);
          return (
            <div key={L.id} className="card doc">
              <div className="ghead" style={{ marginBottom: 10 }}>
                <span className="gid" style={{ fontSize: 14 }}>{L.id}</span>
                <span className="gt" style={{ fontSize: 18 }}>{L.t}</span>
                <span className="gcap">{L.cap}</span>
              </div>

              <div className="callout"><span className="lab">保姆级</span>{L.nanny}</div>

              {L.formula && (<>
                <MB>{L.formula}</MB>
                {L.formulaNote && <p className="formula-note">{L.formulaNote}</p>}
              </>)}
              {L.example && <div className="worked"><span className="lab">数值示例</span>　{L.example}</div>}

              <h3>实现要点</h3>
              <div className="gsub">
                <span className="gk">取样</span><span className="gv">{L.sample}</span>
                <span className="gk">LLM抽</span><span className="gv">{L.how}</span>
                <span className="gk">代码兜底</span><span className="gv">{L.code}</span>
                <span className="gk">输出</span><span className="gv"><code>{L.out}</code></span>
                <span className="gk">进spec</span><span className="gv">{L.spec}</span>
              </div>

              {got && live && (
                <div style={{ marginTop: 12 }}>
                  <div className="eyebrow" style={{ marginBottom: 6 }}>本书实抽 · {slug}</div>
                  {L.key === "lexicon" && live.density_by_scene && <DensityHeat data={live.density_by_scene} />}
                  {L.key === "transition" && live.scene_transition && <TransitionGraph data={live.scene_transition} />}
                  <div className="tablescroll" style={{ maxHeight: 280, padding: "10px 12px" }}>
                    <pre style={{ whiteSpace: "pre-wrap", margin: 0, fontSize: 11.8, lineHeight: 1.6, fontFamily: "var(--mono)" }}>{trim(live)}</pre>
                  </div>
                </div>
              )}
            </div>
          );
        })}

        <div className="card doc">
          <span className="eyebrow">REUSE</span>
          <h2 style={{ marginTop: 4 }}>两档复用 · 从分析产物到生成驱动</h2>
          <ol className="steps">
            <li><b>静态档(软用)</b>:把渲染出的 spec 直接拼进 writer 的 system prompt(<code>compose.seed_genome</code>),零改生成链即生效。</li>
            <li><b>动态档(硬用)</b>:把 L7 转移矩阵当采样器——逐章给定当前状态,采样下一拍 scene_type/张力/POV,取该场景 L5 调度卡 + L6 章型模板 + 待办伏笔栈,组装成"本章导演 brief"再交 writer 填词。这就是"可运行的状态机"。</li>
          </ol>
          <div className="callout zhu"><span className="lab">实测</span>同章大纲,基线(单段总结)vs 基因组(分层 spec)各生成一章、以原著片段为标尺做 7 维盲评:<b>基因组全面胜出</b>(整体 65.25 vs 56.75,场景调度 +10.75,4 场赢 3)。详见「架构 → ⑤ 评测闭环」。</div>
        </div>
      </main>
    </div>
  );
}
