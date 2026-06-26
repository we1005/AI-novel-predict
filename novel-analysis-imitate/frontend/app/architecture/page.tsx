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
  ["L1 lexicon", "词汇分层", "克苏鲁/蒸汽朋克/宗教… 分层词表 + 搭配 + 分场景密度(确定性兜底)"],
  ["L2 syntax", "句式构式", "填空骨架 + 触发场景 + 弱断言滥用红线"],
  ["L3 rhetoric", "修辞·声音", "比喻本体→喻体映射 + FID/叙述距离/心理动词"],
  ["L4 atmosphere", "类型氛围配方", "蒸汽朋克/克苏鲁怎么营造:手段→实现→例证→剂量"],
  ["L5 scene_routine", "场景调度套路", "每类场面:切入机位/节拍序列/详略预算/收尾钩子"],
  ["L6 macro_arch", "宏观架构", "伏笔plant→payoff图/信息预算/张力控制律/章型模板"],
  ["L7 transition", "转移模型", "场景&功能的马尔可夫转移矩阵(Transformer/LSTM 类比)"],
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

        {/* 3 · 文风基因组 7 层 */}
        <div className="card">
          <span className="eyebrow">STYLE GENOME</span>
          <h2>③ 文风基因组 7 层 <span className="tag">把"单段总结"升级成可复现的分层范式</span></h2>
          <div className="archlayer">
            {GENOME.map(([n, t, d]) => (
              <div key={n} className="archrow"><span className="n">{n}</span><span className="t">{t}</span><span className="d">{d}</span></div>
            ))}
          </div>
          <div className="archflow" style={{ marginTop: 14 }}>
            <div className="archbox zhe"><b>7 层抽取</b><span>分场景桶取样 + 确定性兜底</span></div>
            <Arrow />
            <div className="archbox zhe"><b>指纹向量</b><span>可计算文风(密度/弱断言/张力型…)</span></div>
            <Arrow />
            <div className="archbox zhu"><b>system-prompt spec</b><span>喂给任意 LLM 即复现文风</span></div>
            <Arrow />
            <div className="archbox zhu"><b>驱动生成</b><span>compose.seed_genome</span></div>
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
