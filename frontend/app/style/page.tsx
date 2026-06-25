"use client";

import { useEffect, useState, type ReactNode } from "react";
import { Switch, Tag, message, Tooltip } from "antd";
import { HighlightOutlined, ThunderboltOutlined, GlobalOutlined } from "@ant-design/icons";
import { api } from "@/lib/api";
import PageTitle from "@/components/PageTitle";

type Profile = {
  overall_voice?: string;
  narrative_pov?: string;
  sentence_rhythm?: string;
  register?: string;
  scene_styles?: Record<string, string>;
  tropes?: string[];
  signature_vocabulary?: string[];
  structural_habits?: string;
  is_western_setting?: boolean;
  setting_register?: string;
  continuation_guide?: string;
  pitfalls_to_avoid?: string[];
};

type StyleData = {
  id?: number;
  profile: Profile | null;
  summary?: string;
  sampled_chapters?: number[];
  mimic_enabled?: boolean;
  bilingual?: boolean;
  is_western_setting?: boolean;
  era_check_enabled?: boolean;
  culture_check_enabled?: boolean;
  has_register_card?: boolean;
  model?: string;
  cost_usd?: number;
  updated_at?: string;
};

const SCENE_LABEL: Record<string, string> = {
  combat: "打斗 / 动作",
  scenery: "景物 / 氛围",
  character: "人物刻画",
  dialogue: "对话",
  psychology: "心理 / 内心",
  plot_advancement: "剧情推进",
};

export default function StylePage() {
  const [data, setData] = useState<StyleData | null>(null);
  const [loading, setLoading] = useState(true);
  const [analyzing, setAnalyzing] = useState(false);
  const [sampleN, setSampleN] = useState(8);
  const [book, setBook] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const d = await api.styleGet();
      setData(d);
      const bk = await api.booksList();
      setBook(bk?.active || null);
    } catch (e) {
      message.error("加载失败：" + String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const analyze = async () => {
    setAnalyzing(true);
    try {
      const d = await api.styleAnalyze(sampleN);
      setData(d);
      message.success("文笔分析完成");
    } catch (e) {
      message.error("分析失败：" + String(e));
    } finally {
      setAnalyzing(false);
    }
  };

  const toggle = async (field: "mimic_enabled" | "bilingual" | "era_check_enabled" | "culture_check_enabled", val: boolean) => {
    try {
      const d = await api.styleToggle({ [field]: val });
      setData(d);
    } catch (e) {
      message.error("切换失败：" + String(e));
    }
  };

  const [cardBusy, setCardBusy] = useState(false);
  const extractCard = async () => {
    setCardBusy(true);
    try { const r = await api.styleRegisterCard(8); message.success("语域卡已抽取：" + (r.factions || []).join("、")); load(); }
    catch (e) { message.error("抽取失败：" + String(e)); }
    finally { setCardBusy(false); }
  };

  // 续写模式预设：一键设定 mimic / bilingual 开关组合（一套可组合引擎 + 命名预设，
  // 而非硬编码多管线）。
  const applyPreset = async (mimic: boolean, bilingual: boolean, name: string) => {
    try {
      const d = await api.styleToggle({ mimic_enabled: mimic, bilingual });
      setData(d);
      message.success(`已切到「${name}」模式`);
    } catch (e) {
      message.error("切换失败：" + String(e));
    }
  };

  const p = data?.profile || null;
  // 当前激活的预设（用于高亮选中态）
  const activePreset = !data?.mimic_enabled && !data?.bilingual ? "wangwen"
    : data?.mimic_enabled && data?.bilingual ? "bilingual"
    : data?.mimic_enabled ? "mimic" : "custom";
  const PRESETS: { key: string; label: string; desc: string; mimic: boolean; bilingual: boolean }[] = [
    { key: "wangwen", label: "长篇网文", desc: "弃用原作文风 · 明快网文腔", mimic: false, bilingual: false },
    { key: "mimic", label: "传统仿写", desc: "模仿原作者笔法与叙事节奏", mimic: true, bilingual: false },
    { key: "bilingual", label: "西方双语", desc: "仿写 + 中英对照（地道英文技法）", mimic: true, bilingual: true },
  ];

  return (
    <div style={{ maxWidth: 1100 }}>
      <PageTitle title="文笔风格"
        subtitle="分析原作者的行文风格，用于「模仿原作者笔法」的续写（默认关闭，开启较耗 token）" />

      {/* ---- control card ---- */}
      <div className="card">
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
          <div>
            <h3 style={{ margin: 0, display: "flex", alignItems: "center", gap: 8 }}>
              <HighlightOutlined /> 当前书：{book ? <span style={{ color: "var(--accent-2)" }}>《{book}》</span> : "—"}
            </h3>
            {data?.updated_at && (
              <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>
                上次分析：{data.updated_at.replace("T", " ").slice(0, 19)} · 抽样章节 {data.sampled_chapters?.join(", ")} · {data.model} · ${data.cost_usd?.toFixed(4)}
              </div>
            )}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <label style={{ fontSize: 12, color: "var(--muted)" }}>
              抽样
              <input type="number" value={sampleN} min={3} max={20}
                onChange={(e) => setSampleN(Math.max(3, Math.min(20, +e.target.value || 8)))}
                style={{ width: 56, margin: "0 4px", padding: "4px 6px", borderRadius: 6, border: "1px solid var(--border)", background: "var(--panel)", color: "inherit" }} />
              章
            </label>
            <button onClick={analyze} disabled={analyzing} style={{ padding: "8px 18px" }}>
              <ThunderboltOutlined /> {analyzing ? "分析中…（约 1-2 分钟）" : p ? "重新分析" : "分析本书文笔"}
            </button>
          </div>
        </div>

        {/* toggles */}
        {p && (
          <div style={{ display: "flex", gap: 28, marginTop: 16, flexWrap: "wrap" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Switch checked={!!data?.mimic_enabled} onChange={(v) => toggle("mimic_enabled", v)} />
              <span style={{ fontSize: 13 }}>续写时模仿原作者文风</span>
              <Tooltip title="开启后，续写不再用默认的网文笔法，而是按上面分析出的作者风格来写。">
                <span className="muted" style={{ fontSize: 11, cursor: "help" }}>(?)</span>
              </Tooltip>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Switch checked={!!data?.bilingual} onChange={(v) => toggle("bilingual", v)} />
              <span style={{ fontSize: 13 }}><GlobalOutlined /> 双语续写（中英对照）</span>
              {data?.is_western_setting && <Tag color="blue" style={{ fontSize: 10 }}>西方背景 · 推荐</Tag>}
              <Tooltip title="西方背景小说推荐开启：独立生成中/英两版 → 互译对比 → 取长补短融合，用英文行文技法冲淡廉价西幻网文腔。">
                <span className="muted" style={{ fontSize: 11, cursor: "help" }}>(?)</span>
              </Tooltip>
            </div>
          </div>
        )}

        {/* 时代语域审查（第4审 · 默认关 · 每本书可配）*/}
        {p && (
          <div style={{ marginTop: 16, padding: "12px 14px", background: "var(--panel-2)", borderRadius: 8, borderLeft: "3px solid #f7768e" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 8 }}>
              <strong style={{ fontSize: 13 }}>🏛 时代语域审查（第4审 · 默认关）</strong>
              <button onClick={extractCard} disabled={cardBusy} style={{ padding: "2px 10px", fontSize: 12 }}>
                {cardBusy ? "抽取中…" : data?.has_register_card ? "🔄 重抽世界观语域卡" : "📜 抽取世界观语域卡"}
              </button>
              {data?.has_register_card ? <Tag color="green" style={{ fontSize: 10 }}>已有语域卡</Tag> : <Tag style={{ fontSize: 10 }}>无语域卡（需先抽取）</Tag>}
            </div>
            <div style={{ display: "flex", gap: 28, flexWrap: "wrap" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Switch checked={!!data?.era_check_enabled} disabled={!data?.has_register_card} onChange={(v) => toggle("era_check_enabled", v)} />
                <span style={{ fontSize: 13 }}>时代错置层</span>
                <Tooltip title="与阵营无关的硬基线：蒸汽朋克世界里谁都不能冒出现代物/词/网络语（手机、塑料、OK…）。命中硬伤触发返工。">
                  <span className="muted" style={{ fontSize: 11, cursor: "help" }}>(?)</span>
                </Tooltip>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Switch checked={!!data?.culture_check_enabled} disabled={!data?.has_register_card} onChange={(v) => toggle("culture_check_enabled", v)} />
                <span style={{ fontSize: 13 }}>阵营文化语域层</span>
                <Tooltip title="按词的归属角色判：太监属东方阵营在西方场景也对；西方角色说东亚黑话才算错。东西方同台逐元素各判各的。">
                  <span className="muted" style={{ fontSize: 11, cursor: "help" }}>(?)</span>
                </Tooltip>
              </div>
            </div>
            <p className="muted" style={{ fontSize: 11, marginTop: 8, marginBottom: 0 }}>
              纯单一文化的书（纯西方蒸汽朋克 / 纯南宋仙侠）建议开；东西方混合的书（如天之炽）语域卡需覆盖到各阵营再开，否则可能漏判东方阵营。
            </p>
          </div>
        )}

        {/* 续写模式预设：一键组合（mimic / bilingual）*/}
        {p && (
          <div style={{ marginTop: 18, paddingTop: 14, borderTop: "1px dashed var(--border)" }}>
            <div className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
              续写模式预设 — 一键设定上面两个开关的组合（西方背景书推荐「西方双语」）
            </div>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              {PRESETS.map((preset) => {
                const active = activePreset === preset.key;
                return (
                  <button key={preset.key}
                    onClick={() => applyPreset(preset.mimic, preset.bilingual, preset.label)}
                    style={{
                      textAlign: "left", padding: "8px 14px", borderRadius: 8, cursor: "pointer",
                      border: active ? "1px solid var(--accent-2)" : "1px solid var(--border)",
                      background: active ? "rgba(99,102,241,0.12)" : "var(--panel)",
                      color: "inherit", minWidth: 168,
                    }}>
                    <div style={{ fontSize: 13, fontWeight: 600, display: "flex", alignItems: "center", gap: 6 }}>
                      {preset.label}
                      {active && <Tag color="geekblue" style={{ fontSize: 10, marginInlineEnd: 0 }}>当前</Tag>}
                    </div>
                    <div className="muted" style={{ fontSize: 11, marginTop: 2 }}>{preset.desc}</div>
                  </button>
                );
              })}
            </div>
            {activePreset === "custom" && (
              <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>
                当前为自定义组合（仅双语、未模仿）——可点上面任一预设规整。
              </div>
            )}
          </div>
        )}
      </div>

      {loading && <div className="card muted">加载中…</div>}

      {!loading && !p && (
        <div className="card muted" style={{ textAlign: "center", padding: "40px 20px" }}>
          还没有这本书的文笔分析。点上方「分析本书文笔」，会抽样若干章节让模型逆向解析作者风格。
        </div>
      )}

      {p && (
        <>
          {/* overall */}
          <div className="card" style={{ borderLeft: "4px solid var(--accent-2)" }}>
            <h3 style={{ marginTop: 0 }}>整体文风
              {p.is_western_setting && <Tag color="blue" style={{ marginLeft: 8 }}>西方/奇幻背景</Tag>}
            </h3>
            <p className="prose-cn" style={{ fontSize: 14, lineHeight: 1.7 }}>{renderVal(p.overall_voice)}</p>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 12, marginTop: 10 }}>
              <Field label="叙事视角" v={p.narrative_pov} />
              <Field label="句式 / 节奏" v={p.sentence_rhythm} />
              <Field label="语域" v={p.register} />
              <Field label="结构习惯" v={p.structural_habits} />
              <Field label="世界观 / 文化语域" v={p.setting_register} />
            </div>
          </div>

          {/* scene styles */}
          {p.scene_styles && (
            <div className="card">
              <h3 style={{ marginTop: 0 }}>分场景笔法</h3>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))", gap: 12 }}>
                {Object.entries(p.scene_styles).map(([k, v]) => (
                  <div key={k} style={{ background: "var(--panel-2)", borderRadius: 8, padding: 12, borderTop: "3px solid var(--accent)" }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: "var(--accent)", marginBottom: 4 }}>
                      {SCENE_LABEL[k] || k}
                    </div>
                    <div style={{ fontSize: 13, lineHeight: 1.6 }}>{renderVal(v)}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* tropes + vocabulary — minWidth:0 防止长串撑破 grid 轨道、挤压邻列 */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 16 }}>
            {p.tropes && p.tropes.length > 0 && (
              <div className="card" style={{ minWidth: 0 }}>
                <h3 style={{ marginTop: 0 }}>常用套路 / 母题</h3>
                <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, lineHeight: 1.8, overflowWrap: "anywhere" }}>
                  {p.tropes.map((t, i) => <li key={i}>{renderVal(t)}</li>)}
                </ul>
              </div>
            )}
            {p.signature_vocabulary && p.signature_vocabulary.length > 0 && (
              <div className="card" style={{ minWidth: 0 }}>
                <h3 style={{ marginTop: 0 }}>标志性词汇 / 意象</h3>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                  {/* 模型可能把整段「A、B、C…」塞成一个元素 → 按顿号/逗号拆成多个标签 */}
                  {p.signature_vocabulary
                    .flatMap((w) => cleanMd(w).split(/[、,，]/))
                    .map((w) => w.trim())
                    .filter(Boolean)
                    .map((w, i) => (
                      <Tag key={i} style={{ fontSize: 12, padding: "2px 8px", whiteSpace: "normal", overflowWrap: "anywhere", maxWidth: "100%" }}>{w}</Tag>
                    ))}
                </div>
              </div>
            )}
          </div>

          {/* continuation guide */}
          {p.continuation_guide && (
            <div className="card" style={{ borderLeft: "4px solid var(--good)" }}>
              <h3 style={{ marginTop: 0 }}>续写指导（喂给写作 agent）</h3>
              <div className="prose-cn" style={{ fontSize: 14, lineHeight: 1.75, overflowWrap: "anywhere" }}>{renderVal(p.continuation_guide)}</div>
            </div>
          )}

          {/* pitfalls */}
          {p.pitfalls_to_avoid && p.pitfalls_to_avoid.length > 0 && (
            <div className="card" style={{ borderLeft: "4px solid var(--bad)" }}>
              <h3 style={{ marginTop: 0 }}>模仿时务必避免</h3>
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, lineHeight: 1.8, overflowWrap: "anywhere" }}>
                {/* 模型常把多条"避免…"用 ； 串进一个元素 → 按分号拆开,每条各自成项 */}
                {p.pitfalls_to_avoid
                  .flatMap((t) => cleanMd(t).split(/[；;]/))
                  .map((t) => t.trim())
                  .filter(Boolean)
                  .map((t, i) => <li key={i} style={{ marginBottom: 4 }}>{t}</li>)}
              </ul>
            </div>
          )}
        </>
      )}

      {/* bilingual continuation */}
      {data?.bilingual && <BilingualPanel />}

      {/* re-voice (推翻文笔保留主干剧情) — available for any book */}
      <RevoicePanel hasMimic={!!data?.profile} />
    </div>
  );
}

function RevoicePanel({ hasMimic }: { hasMimic: boolean }) {
  const [chapter, setChapter] = useState<number>(1);
  const [voice, setVoice] = useState<"wangwen" | "mimic" | "english">("wangwen");
  const [job, setJob] = useState<any | null>(null);
  const [running, setRunning] = useState(false);
  const [history, setHistory] = useState<any[]>([]);

  const loadHistory = () => api.revoiceList().then(setHistory).catch(() => {});
  useEffect(() => { loadHistory(); }, []);

  useEffect(() => {
    if (!job || job.status !== "writing") return;
    const t = setInterval(async () => {
      try {
        const d = await api.revoiceGet(job.id);
        setJob(d);
        if (d.status !== "writing") { setRunning(false); loadHistory(); clearInterval(t); }
      } catch { /* noop */ }
    }, 5000);
    return () => clearInterval(t);
  }, [job?.id, job?.status]);

  const VOICE_LABEL: Record<string, string> = { wangwen: "网文（明快爽利）", mimic: "仿写原作者", english: "英文（母语技法）" };

  const start = async () => {
    setRunning(true);
    try {
      const r = await api.revoiceStart({ voice, source_chapter: chapter });
      setJob(r);
      message.success("已开始重写（保留剧情主干，替换文笔）");
    } catch (e) { message.error("启动失败：" + String(e)); setRunning(false); }
  };

  return (
    <div className="card" style={{ borderLeft: "4px solid var(--c-subplot)" }}>
      <h3 style={{ marginTop: 0, display: "flex", alignItems: "center", gap: 8 }}>
        🔁 推翻文笔 · 保留主干剧情重写
      </h3>
      <p className="muted" style={{ fontSize: 12, marginTop: -4 }}>
        先把指定章节拆成剧情骨架（事件/关键信息/钩子），再用目标文笔重写——剧情完全不变，只换文风。适合"剧情好但文笔不满意"的章节。
      </p>
      <div style={{ display: "flex", gap: 12, alignItems: "flex-end", flexWrap: "wrap", marginTop: 8 }}>
        <label style={{ fontSize: 12, color: "var(--muted)" }}>
          重写第
          <input type="number" value={chapter} min={1}
            onChange={(e) => setChapter(Math.max(1, +e.target.value || 1))}
            style={{ width: 70, margin: "0 4px", padding: "6px 8px", borderRadius: 6, border: "1px solid var(--border)", background: "var(--panel)", color: "inherit" }} />
          章
        </label>
        <label style={{ fontSize: 12, color: "var(--muted)" }}>
          目标文笔
          <select value={voice} onChange={(e) => setVoice(e.target.value as any)}
            style={{ marginLeft: 4, padding: "6px 8px", borderRadius: 6, border: "1px solid var(--border)", background: "var(--panel)", color: "inherit" }}>
            <option value="wangwen">网文（明快爽利）</option>
            <option value="mimic" disabled={!hasMimic}>仿写原作者{hasMimic ? "" : "（需先分析文笔）"}</option>
            <option value="english">英文（母语技法）</option>
          </select>
        </label>
        <button onClick={start} disabled={running} style={{ padding: "8px 18px" }}>
          {running ? "重写中…" : "重写本章"}
        </button>
      </div>

      {history.length > 0 && (
        <div style={{ marginTop: 12, display: "flex", gap: 6, flexWrap: "wrap" }}>
          {history.map((h) => (
            <button key={h.id} className="ghost" onClick={() => api.revoiceGet(h.id).then(setJob)}
              style={{ padding: "3px 10px", fontSize: 11, borderColor: job?.id === h.id ? "var(--c-subplot)" : "var(--border)" }}>
              #{h.id} 第{h.source_chapter}章·{VOICE_LABEL[h.voice]?.slice(0, 2)} {h.status === "done" ? "✓" : h.status === "failed" ? "✗" : "…"}
            </button>
          ))}
        </div>
      )}

      {job && (
        <div style={{ marginTop: 14 }}>
          {job.status === "writing" && <p className="muted">⏳ 拆解剧情骨架 → 换文笔重写…约 2-3 分钟。</p>}
          {job.status === "failed" && <p style={{ color: "var(--bad)" }}>失败：{job.error}</p>}
          {job.status === "done" && (
            <div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) minmax(0,1.4fr)", gap: 14 }}>
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: "var(--muted)", marginBottom: 6 }}>剧情骨架（保持不变）</div>
                <div style={{ background: "var(--panel-2)", borderRadius: 6, padding: 12, maxHeight: 560, overflow: "auto", fontSize: 12.5, lineHeight: 1.6 }}>
                  {(job.skeleton?.beats || []).map((b: string, i: number) => (
                    <div key={i} style={{ marginBottom: 6 }}>{i + 1}. {b}</div>
                  ))}
                  {job.skeleton?.ending_hook && <div style={{ marginTop: 8, color: "var(--c-mystery)" }}>钩子：{job.skeleton.ending_hook}</div>}
                </div>
              </div>
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: "var(--c-subplot)", marginBottom: 6 }}>重写正文 · {VOICE_LABEL[job.voice]}</div>
                <pre style={{ whiteSpace: "pre-wrap", fontFamily: 'ui-serif, "PingFang SC", serif', fontSize: 13.5, lineHeight: 1.75, background: "var(--panel-2)", padding: 14, borderRadius: 6, margin: 0, maxHeight: 560, overflow: "auto" }}>{job.rewritten}</pre>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

const BILINGUAL_STAGES: { key: string; label: string }[] = [
  { key: "zh_draft", label: "中文稿" },
  { key: "en_recreate", label: "英文再创作" },
  { key: "translate", label: "交叉互译" },
  { key: "merge", label: "取长补短融合" },
];

function BilingualStageBar({ stage }: { stage?: string }) {
  // index of the currently-running stage; unknown/empty → first stage
  const cur = Math.max(0, BILINGUAL_STAGES.findIndex((s) => s.key === stage));
  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap", marginBottom: 6 }}>
        {BILINGUAL_STAGES.map((s, i) => {
          const done = i < cur, active = i === cur;
          return (
            <span key={s.key} style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{
                fontSize: 12, padding: "3px 10px", borderRadius: 12,
                border: active ? "1px solid var(--accent-2)" : "1px solid var(--border)",
                background: active ? "rgba(99,102,241,0.15)" : done ? "var(--panel-2)" : "transparent",
                color: done ? "var(--muted)" : active ? "var(--accent-2)" : "var(--muted)",
                fontWeight: active ? 600 : 400,
              }}>
                {done ? "✓ " : active ? "⏳ " : ""}{s.label}
              </span>
              {i < BILINGUAL_STAGES.length - 1 && <span className="muted" style={{ fontSize: 11 }}>→</span>}
            </span>
          );
        })}
      </div>
      <p className="muted" style={{ margin: 0, fontSize: 12 }}>
        以中文稿为蓝本生成地道英文再创作 → 交叉互译 → 融合。约 5-15 分钟（minimax-m3 融合较慢），完成后自动显示。
      </p>
    </div>
  );
}

function BilingualPanel() {
  const [brief, setBrief] = useState("承接上一章结尾的悬念，主线向前推进但不揭底，节奏先紧后缓再起悬念，章末留强钩子。保持悬疑。");
  const [afterChapter, setAfterChapter] = useState<number>(0);
  const [job, setJob] = useState<any | null>(null);
  const [running, setRunning] = useState(false);
  const [history, setHistory] = useState<any[]>([]);

  const loadHistory = () => api.bilingualList().then(setHistory).catch(() => {});
  useEffect(() => {
    loadHistory();
    api.chapterCount().then((c: any) => setAfterChapter(c?.last || c?.total || 0)).catch(() => {});
  }, []);

  // poll an active job
  useEffect(() => {
    if (!job || job.status !== "writing") return;
    const t = setInterval(async () => {
      try {
        const d = await api.bilingualGet(job.id);
        setJob(d);
        if (d.status !== "writing") { setRunning(false); loadHistory(); clearInterval(t); }
      } catch { /* noop */ }
    }, 5000);
    return () => clearInterval(t);
  }, [job?.id, job?.status]);

  const start = async () => {
    setRunning(true);
    try {
      const r = await api.bilingualStart({ brief, after_chapter: afterChapter });
      setJob(r);
      message.success("已开始双语续写（约 4-6 分钟，5 个 agent）");
    } catch (e) {
      message.error("启动失败：" + String(e));
      setRunning(false);
    }
  };

  const openJob = async (id: number) => {
    try { setJob(await api.bilingualGet(id)); } catch { /* noop */ }
  };

  return (
    <div className="card" style={{ borderLeft: "4px solid var(--accent-2)" }}>
      <h3 style={{ marginTop: 0, display: "flex", alignItems: "center", gap: 8 }}>
        <GlobalOutlined /> 双语续写（中 / 英 交叉翻译融合）
      </h3>
      <p className="muted" style={{ fontSize: 12, marginTop: -4 }}>
        独立写中文(模仿原作者)+英文(母语技法) → 互译对比 → 取长补短融合，产出最终中英双版。用英文行文技法冲淡廉价西幻网文腔。
      </p>

      <div style={{ display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap", marginTop: 8 }}>
        <label style={{ flex: 1, minWidth: 280, fontSize: 12, color: "var(--muted)" }}>
          本章要求 / 剧情走向
          <textarea value={brief} onChange={(e) => setBrief(e.target.value)} rows={3}
            style={{ width: "100%", marginTop: 4, padding: 8, borderRadius: 6, border: "1px solid var(--border)", background: "var(--panel)", color: "inherit", fontSize: 13 }} />
        </label>
        <label style={{ fontSize: 12, color: "var(--muted)" }}>
          续写第
          <input type="number" value={afterChapter + 1}
            onChange={(e) => setAfterChapter(Math.max(0, (+e.target.value || 1) - 1))}
            style={{ width: 70, margin: "0 4px", padding: "6px 8px", borderRadius: 6, border: "1px solid var(--border)", background: "var(--panel)", color: "inherit" }} />
          章
        </label>
        <button onClick={start} disabled={running} style={{ padding: "8px 18px" }}>
          {running ? "生成中…" : "生成双语续写"}
        </button>
      </div>

      {history.length > 0 && (
        <div style={{ marginTop: 12, display: "flex", gap: 6, flexWrap: "wrap" }}>
          {history.map((h) => (
            <button key={h.id} className="ghost" onClick={() => openJob(h.id)}
              style={{ padding: "3px 10px", fontSize: 11, borderColor: job?.id === h.id ? "var(--accent-2)" : "var(--border)" }}>
              #{h.id} 第{h.chapter}章 · {h.status === "done" ? "✓" : h.status === "failed" ? "✗" : "…"}
            </button>
          ))}
        </div>
      )}

      {job && (
        <div style={{ marginTop: 14 }}>
          {job.status === "writing" && <BilingualStageBar stage={job.stage} />}
          {job.status === "failed" && <p style={{ color: "var(--bad)" }}>失败：{job.error}</p>}
          {job.status === "done" && (
            <>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
                <div>
                  <div style={{ fontSize: 12, fontWeight: 600, color: "var(--accent-2)", marginBottom: 6 }}>中文版（终稿）</div>
                  <pre style={{ whiteSpace: "pre-wrap", fontFamily: 'ui-serif, "PingFang SC", serif', fontSize: 13.5, lineHeight: 1.75, background: "var(--panel-2)", padding: 14, borderRadius: 6, margin: 0, maxHeight: 620, overflow: "auto" }}>{job.final_zh}</pre>
                </div>
                <div>
                  <div style={{ fontSize: 12, fontWeight: 600, color: "var(--accent-2)", marginBottom: 6 }}>English (final)</div>
                  <pre style={{ whiteSpace: "pre-wrap", fontFamily: 'Georgia, ui-serif, serif', fontSize: 13.5, lineHeight: 1.7, background: "var(--panel-2)", padding: 14, borderRadius: 6, margin: 0, maxHeight: 620, overflow: "auto" }}>{job.final_en}</pre>
                </div>
              </div>
              {/* 融合过程回溯：4 个中间版本 */}
              {job.drafts && (
                <details style={{ marginTop: 12 }}>
                  <summary style={{ cursor: "pointer", fontSize: 12, color: "var(--muted)" }}>
                    🔍 查看融合过程（中英各 2 个原始版本 → 取长补短得终稿，可回溯）
                  </summary>
                  <p className="muted" style={{ fontSize: 11, margin: "6px 0" }}>
                    终稿英文 ≈ 70% 英文原创(母语技法) + 30% 中→英(原作意象)；终稿中文 ≈ 70% 中文原创(原作文风) + 30% 英→中(英文克制感)。
                  </p>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginTop: 4 }}>
                    {[
                      ["中文·原创（仿原作者）", job.drafts.zh_orig, 'ui-serif, "PingFang SC", serif'],
                      ["英文·原创（母语技法）", job.drafts.en_orig, "Georgia, serif"],
                      ["中←英（英文版回译）", job.drafts.zh_from_en, 'ui-serif, "PingFang SC", serif'],
                      ["英←中（中文版翻译）", job.drafts.en_from_zh, "Georgia, serif"],
                    ].map(([label, text, font], i) => (
                      <div key={i}>
                        <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 4 }}>{label as string}</div>
                        <pre style={{ whiteSpace: "pre-wrap", fontFamily: font as string, fontSize: 12, lineHeight: 1.6, background: "var(--bg)", border: "1px solid var(--border)", padding: 10, borderRadius: 6, margin: 0, maxHeight: 280, overflow: "auto" }}>{(text as string) || "（无）"}</pre>
                      </div>
                    ))}
                  </div>
                </details>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

// 把任意值(字符串/数组/对象)渲染成可读文本——模型偶尔把本应是字符串的
// 字段(如 structural_habits)返回成对象 {chapter_title, chapter_ending, …},
// 直接当 React child 渲染会抛 "Objects are not valid as a React child"。
// 去掉模型偶尔夹带的 markdown 标记(** 加粗、行首 - / * 列表符),避免字面显示。
function cleanMd(s: any): string {
  return String(s)
    .replace(/\*\*/g, "")            // 去 markdown 加粗
    .replace(/^\s*[-*]\s+/, "")       // 去行首列表符
    .replace(/^["'\s]+/, "")          // 去行首残留引号/空白(模型常在条目前加 ")
    .trim();
}

function renderVal(v: any): ReactNode {
  if (v == null) return null;
  if (typeof v === "string") {
    // 多行字符串(如续写指导:模型把 "1. / 2." 结构 + "- " 列表塞进一个字段)
    // 逐行渲染:行首 "- " 转成缩进项目符号 ·,其余行原样,避免满屏字面 "-"。
    if (v.includes("\n")) {
      const lines = v.split("\n");
      return (
        <div style={{ display: "grid", gap: 3 }}>
          {lines.map((ln, i) => {
            const bullet = /^\s*[-*]\s+/.test(ln);
            const t = cleanMd(ln);
            if (!t) return null;
            return (
              <div key={i} style={bullet ? { paddingLeft: 16, textIndent: "-12px" } : undefined}>
                {bullet ? "· " : ""}{t}
              </div>
            );
          })}
        </div>
      );
    }
    return cleanMd(v);
  }
  if (typeof v === "number") return v;
  if (Array.isArray(v)) {
    return (
      <ul style={{ margin: 0, paddingLeft: 18 }}>
        {v.map((x, i) => <li key={i}>{renderVal(x)}</li>)}
      </ul>
    );
  }
  if (typeof v === "object") {
    return (
      <div style={{ display: "grid", gap: 4 }}>
        {Object.entries(v).map(([k, val]) => (
          <div key={k}>
            <span style={{ color: "var(--muted)" }}>{k}：</span>
            <span>{renderVal(val)}</span>
          </div>
        ))}
      </div>
    );
  }
  return String(v);
}

function Field({ label, v }: { label: string; v?: any }) {
  if (v == null || v === "") return null;
  return (
    <div>
      <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: 13, lineHeight: 1.6 }}>{renderVal(v)}</div>
    </div>
  );
}
