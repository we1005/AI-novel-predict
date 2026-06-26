"use client";
import Icon from "@/components/Icon";
import Link from "next/link";

function Rail() {
  return (
    <aside className="rail">
      <Link href="/" className="railbrand"><span className="railseal">墨</span><span>墨析</span></Link>
      <nav className="railnav">
        <Link href="/" className="railitem"><Icon k="analyze" /><span>深度分析</span></Link>
        <Link href="/generate" className="railitem"><Icon k="compose" /><span>仿写 · 重组</span></Link>
        <Link href="/architecture" className="railitem active"><Icon k="arch" /><span>架构</span></Link>
      </nav>
      <div className="railsection">专页</div>
      <Link href="/genome" className="railitem"><Icon k="style" /><span>文风基因组</span></Link>
    </aside>
  );
}

const Arrow = () => <div className="archarrow">→</div>;

const LAYERS = [
  ["base", "基础抽取", "复用主项目 6 抽取 agent + 关系图:实体/伏笔/剧情点/世界规则/关系网"],
  ["speedread", "速读脉络", "按章序切阶段,重要阶段详写(发生/伏笔/内心/转折/线索)"],
  ["pacing", "节拍张力", "逐章张力/场景类型/plot_function/章末钩子 → 张力曲线"],
  ["style", "文笔声音", "整体声音/句式/语域/常用词汇/套路/范文(StyleProfile)"],
  ["worldview", "世界观铺垫", "设定揭示事件:手法/信息倾倒率/埋设跨度(江南式反倾倒)"],
  ["relationship", "人物关系", "关系演变事件 + 网络图 + 主要人物简介卡"],
  ["pov", "视角调度", "POV 切换时间轴:离开主角时长/切回触发"],
  ["golden", "金手指", "升级台阶/触发方式/对手差距 → 升级斜率"],
];

const GENOME = [
  {
    id: "L1", t: "词汇分层", cap: "用词调色盘:每层词在什么场景该撒多浓",
    sample: "按 scene_type 分桶,每桶取张力最高的代表章原文(spread + bucket)",
    how: "LLM 把实词归入语义场(克苏鲁不可名状/蒸汽朋克器物/宗教/感官身体/军事…),只收原文真出现的词 + 逐字共现搭配,不许编造",
    code: "每层词在每个场景桶里 str.count/千字 → density_by_scene,LLM 估值不准就用代码兜底",
    out: "strata:[{layer, signature_words, collocations, trigger_context}], diction, avoid(廉价网文词黑名单)",
    spec: "渲染成『用词调色盘』:每层标志词 + 该类场景密度配比",
  },
  {
    id: "L2", t: "句式构式", cap: "可填空的句式骨架库,不是一句话节奏总结",
    sample: "按 scene_type×plot_function 分桶;直接复用 craft 26 类已切好的逐字片段(省 token)",
    how: "LLM 抽反复出现的句式构造,抽象成带槽模板(如『随着[X],[Y]』),给触发场景/效果/逐字例",
    code: "弱断言(似乎/仿佛)用正则全书计数得 authentic_rate;LLM 只判滥用红线倍数 → 防网文腔",
    out: "templates:[{skeleton, trigger_scenes, freq_band, exemplars, misuse_redline}], hedge_usage, rhythm",
    spec: "『句式骨架库』:填空模板 + 频率上限 + 滥用红线",
  },
  {
    id: "L3", t: "修辞 · 叙述声音", cap: "比喻怎么打 + 叙述者站多近、是否议论",
    sample: "煽情/悬疑/人物刻画桶权重高;复用 craft 的 signature_metaphor/interior/monologue 片段",
    how: "LLM 逐条记比喻 [本体]→[喻体] 并归语义场;分析叙述距离/自由间接引语(FID)/旁白评议/心理动词/反问",
    code: "叠词、省略号独段用正则全书计数补强",
    out: "metaphor_map{favored,vehicle_dist}, reduplications, narrator{distance,fid_examples,psych_verbs}",
    spec: "『修辞与叙述者操作手册』:喻体取向 + FID/距离 + 招牌一招",
  },
  {
    id: "L4", t: "类型氛围配方", cap: "蒸汽朋克/克苏鲁到底靠什么手段营造",
    sample: "高氛围取样:scene_type∈{悬疑惊悚,大高潮} 且张力≥70 + 世界观揭示命中超自然概念的章",
    how: "分类型拆 carrier:means(回避命名/感官失序/理智代价/器物密度/能源-机械隐喻…)→how→逐字例证,并给黄金律",
    code: "carrier 词在对应场景桶 str.count/千字 → 剂量",
    out: "genres:[{genre, techniques:[{means,how,intensity,examples,density}], golden_rule, lexicon{do,avoid}}]",
    spec: "每质感一张『配方卡』+ 黄金律(如克苏鲁:永不正面写本体,只写反应与代价)",
  },
  {
    id: "L5", t: "场景调度套路", cap: "写某类场面的『分场拍摄剧本』(最补缺陷的一层)",
    sample: "每类 scene_type 取**整场全文(不截断)**6-10 场,优先高潮/强钩子章(顺序是命门)",
    how: "LLM 逆向写作程序:从哪切入(机位枚举)→节拍数组(每拍 function+镜头+字数占比)→详略五分类%→POV距离→收尾钩子模板",
    code: "聚合:opening_cut 算分布、beat_function 序列做 bigram 转移、详略/字数占比求均",
    out: "routines:[{scene_type, opening_cut{dist}, modal_beat_sequence, detail_budget, exit{hook_grammar,hook_template}}]",
    spec: "『分场景调度手册』:每类场面 切入→节拍链→详略→钩子模板",
  },
  {
    id: "L6", t: "宏观架构", cap: "片段法抓不到的整体结构(关系/序列/转移)",
    sample: "大部分纯代码:复用既有 foreshadowing 表 + chapter_beat 全序列 + pov_event + 速读阶段",
    how: "伏笔账本(plant→payoff跨度/长线比)、信息预算(逐章载体/drip序列)、章型模板由 LLM 切 macro-block 序列再聚类",
    code: "张力控制律(峰检测/上升斜率/回落/峰间距分位)、POV调度、伏笔跨度统计 全为纯代码",
    out: "foreshadow{threads,stats}, info_budget, tension_law, pov_schedule, chapter_type_templates",
    spec: "『宏观编排纪律』:伏笔中位跨度/反信息倾倒红线/张力控制律/POV调度规则",
  },
  {
    id: "L7", t: "转移模型", cap: "状态→下一步倾向,你说的 Transformer/LSTM 那种",
    sample: "纯代码:chapter_beat 的 scene_type / plot_function 序列",
    how: "对相邻状态计数→归一成转移概率,得一阶(可扩二阶)马尔可夫矩阵 + 每状态最可能的下一拍",
    code: "全为确定性矩阵计算,零 LLM",
    out: "scene_transition{a:{b:prob}}, plot_function_transition, most_likely_next",
    spec: "『场景递进倾向表』:上一拍→最可能的下一拍,可当采样器逐章驱动",
  },
];

const UCS = [
  ["UC2", "文风迁移", "用 A 的文风(或基因组 spec)写你的故事"],
  ["UC1", "融合世界观+文风", "多书融合 fused_worldview/style → 写自创剧情"],
  ["UC4", "技法注入", "把 technique_template 逐章约束节奏/POV/铺垫"],
  ["UC3", "剧情移植", "抽 A/B/C 去设定剧情母核 → 重锚定到新世界观 → 用其文风写"],
];

export default function Architecture() {
  return (
    <div className="applayout">
      <Rail />
      <main className="appmain">
        <span className="eyebrow">SYSTEM · ARCHITECTURE</span>
        <div className="h1">墨析 · 系统架构</div>
        <div className="sub">从原著到「可复现文风」:拆解 → 基因组 → 生成 → 评测闭环。一图看懂整条管线。</div>

        {/* 1 · 总览管线 */}
        <div className="card">
          <span className="eyebrow">PIPELINE</span>
          <h2>① 总览数据流</h2>
          <div className="archflow">
            <div className="archbox qing"><b>原著 .txt</b><span>导入 + 编码探测</span></div>
            <Arrow />
            <div className="archbox qing"><b>切分 / FTS</b><span>章节切分 + BM25 全文</span></div>
            <Arrow />
            <div className="archbox zhe"><b>多层分析</b><span>基础抽取 + 8 分析层 + 文风基因组</span></div>
            <Arrow />
            <div className="archbox zhe"><b>分析产物</b><span>per-book novel.db + 指纹 + spec</span></div>
            <Arrow />
            <div className="archbox zhu"><b>compose 虚拟书</b><span>载入声音/笔法/基因组</span></div>
            <Arrow />
            <div className="archbox zhu"><b>生成内核</b><span>arc→outline→draft 三审一编辑</span></div>
            <Arrow />
            <div className="archbox zhu"><b>新作</b><span>仿写 / 重组</span></div>
          </div>
          <div className="archnote">复用边界:整套既有 backend(LLM客户端/抽取/风格/笔法/生成内核)当包 import,墨析只加"时间轴/技法/基因组"新层 + 跨书编排。全程 <b>book_scope</b> 进程级绑定,多进程并发不串库。</div>
        </div>

        {/* 2 · 分析层矩阵 */}
        <div className="card">
          <span className="eyebrow">ANALYSIS LAYERS</span>
          <h2>② 深度分析维度</h2>
          <div className="archgrid">
            {LAYERS.map(([k, t, d]) => (
              <div key={k} className="archcard">
                <div className="ic"><Icon k={["pacing","style","worldview","relationship","pov","golden","speedread"].includes(k) ? k : "analyze"} /></div>
                <h4>{t}</h4><p>{d}</p>
              </div>
            ))}
          </div>
        </div>

        {/* 3 · 文风基因组 7 层(细化) */}
        <div className="card">
          <span className="eyebrow">STYLE GENOME</span>
          <h2>③ 文风基因组 · 怎么实现 <span className="tag">把"单段总结"升级成可复现的分层范式</span></h2>
          <div style={{ marginBottom: 10 }}><Link href="/genome" className="btn" style={{ display: "inline-block", textDecoration: "none" }}>查看专页:七层详解 + 真实抽取样例 →</Link></div>
          <p style={{ fontSize: 13.5, lineHeight: 1.8, color: "var(--ink)", margin: "0 0 14px" }}>
            核心思路:<b>定性的范式一律挂上频率/密度,且按场景类型路由</b>——把"风格"从一个全局常量,
            升级成<b>可路由的状态机</b>,根治"全程一个腔"。每层都是「<b>分桶取样 → LLM 抽范式 → 纯代码兜底量化 → 落结构化 JSON</b>」,
            最后组装成<b>可计算指纹</b> + <b>可喂给别的 LLM 的 system-prompt</b>。
          </p>

          {/* 总管线 */}
          <div className="pipe">
            <div className="pb k1"><b>分桶取样</b>按 scene_type×POV<br/>整场不截断</div>
            <div className="pa">→</div>
            <div className="pb k2"><b>逐层抽取</b>LLM 抽范式<br/>+ 代码兜底量化</div>
            <div className="pa">→</div>
            <div className="pb k2"><b>组装</b>7层卡<br/>+ 指纹向量</div>
            <div className="pa">→</div>
            <div className="pb k3"><b>双档渲染</b>静态 spec /<br/>动态逐章 brief</div>
            <div className="pa">→</div>
            <div className="pb k3"><b>驱动 writer</b>seed_genome<br/>仿写</div>
            <div className="pa">→</div>
            <div className="pb k3"><b>对账回灌</b>同schema扫产出<br/>→指纹diff→修spec</div>
          </div>

          {/* 逐层详解 */}
          {GENOME.map((g) => (
            <div key={g.id} className="gstep">
              <div className="ghead"><span className="gid">{g.id}</span><span className="gt">{g.t}</span><span className="gcap">{g.cap}</span></div>
              <div className="gsub">
                <span className="gk">取样</span><span className="gv">{g.sample}</span>
                <span className="gk">LLM抽</span><span className="gv">{g.how}</span>
                <span className="gk">代码兜底</span><span className="gv">{g.code}</span>
                <span className="gk">输出</span><span className="gv"><code>{g.out}</code></span>
                <span className="gk">进spec</span><span className="gv">{g.spec}</span>
              </div>
            </div>
          ))}

          <div className="archnote">
            <b>两档复用</b>:① 静态档——把 spec 拼进 writer 的 system prompt,零改生成链直接软约束;
            ② 动态档——把 L7 转移矩阵当采样器,逐章给定当前状态采样下一拍的 scene_type/张力/POV,
            取该场景的 L5 调度卡 + L6 章型模板 + 待办伏笔栈,组装成"本章导演 brief"再交 writer 填词
            (这就是 ML 类比里"可运行的状态机":基因组既能当 JSON 存,又能当采样策略逐章驱动)。
          </div>
        </div>

        {/* 4 · 生成用例 */}
        <div className="card">
          <span className="eyebrow">USE CASES</span>
          <h2>④ 四类生成用例(compose 虚拟书共用一条生成路径)</h2>
          <div className="archgrid">
            {UCS.map(([k, t, d]) => (
              <div key={k} className="archcard">
                <div className="ic"><Icon k="compose" /></div>
                <h4>{k} · {t}</h4><p>{d}</p>
              </div>
            ))}
          </div>
        </div>

        {/* 5 · 评测闭环 */}
        <div className="card">
          <span className="eyebrow">EVAL LOOP</span>
          <h2>⑤ 评测闭环:基线 vs 基因组</h2>
          <div className="archflow">
            <div className="archbox"><b>同章大纲</b><span>覆盖打斗/悬疑/煽情/转场</span></div>
            <Arrow />
            <div className="archbox qing"><b>A 基线</b><span>单段总结 + 范文</span></div>
            <div className="archbox zhu"><b>B 基因组</b><span>分层 spec</span></div>
            <Arrow />
            <div className="archbox zhe"><b>7维盲评 + 指纹对账</b><span>对照原著逐维打分 / KL·余弦 diff</span></div>
            <Arrow />
            <div className="archbox zhu"><b>结论 + 回灌</b><span>偏差报告 → 精修 spec 约束</span></div>
          </div>
          <div className="archnote">实测(《余烬之铳》):基因组 B 7 维全面领先(整体 65.25 vs 56.75,场景调度 +10.75),4 场赢 3。据评委反馈已把"群像多机位/时代保真/去仪表盘化"等约束写回 spec。</div>
        </div>

        {/* 6 · 工程基座 */}
        <div className="card">
          <span className="eyebrow">FOUNDATIONS</span>
          <h2>⑥ 关键工程决策</h2>
          <div className="archgrid">
            <div className="archcard"><h4>book_scope 绑定</h4><p>contextvar 进程级锁定当前书,无视共享 active 指针 → 多进程并发抽取不写串库。</p></div>
            <div className="archcard"><h4>多服务商路由</h4><p>FAST/STRONG lane;当前全链路走小米 MiMo(火山额度告急切换),JSON-in-text + json_repair 兜底。</p></div>
            <div className="archcard"><h4>复用而非重造</h4><p>基础抽取/风格/笔法/生成内核全 import 既有 backend,墨析只加新层,零改原项目。</p></div>
            <div className="archcard"><h4>确定性兜底</h4><p>密度/频率/张力峰/转移矩阵用纯代码算,避免 LLM 估值漂移;指纹可逐维对账。</p></div>
          </div>
        </div>
      </main>
    </div>
  );
}
