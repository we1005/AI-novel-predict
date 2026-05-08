"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Slider,
  InputNumber,
  Tag,
  Tooltip,
  message,
  Modal,
  Empty,
} from "antd";
import {
  ThunderboltOutlined,
  RocketOutlined,
  DatabaseOutlined,
  BulbOutlined,
  EditOutlined,
  TeamOutlined,
  ExperimentOutlined,
  ReloadOutlined,
  SaveOutlined,
  CheckCircleFilled,
  KeyOutlined,
  EyeOutlined,
  EyeInvisibleOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  LinkOutlined,
} from "@ant-design/icons";
import { api } from "@/lib/api";
import PageTitle from "@/components/PageTitle";

type Model = {
  id: string;
  label: string;
  tier: "max" | "plus" | "flash";
  tag: string;
  price_in: number;
  price_out: number;
  desc: string;
};

type Override = {
  model: string | null;
  temperature: number | null;
  max_tokens: number | null;
  top_p: number | null;
};

type AgentRow = {
  id: string;
  group: string;
  lane: "fast" | "strong";
  desc: string;
  defaults: { model: string; temperature: number; max_tokens: number; top_p: number | null };
  overrides: Override;
};

type Lane = { id: "fast" | "strong"; label: string; current: string };

type SettingsBundle = {
  settings: {
    default_model_fast: string;
    default_model_strong: string;
    api_key: string;            // masked
    api_key_set: boolean;
    api_key_source: "settings" | "env" | "none";
    base_url: string;
    effective_base_url: string;
    agents: Record<string, Override>;
  };
  agents: AgentRow[];
  models: Model[];
  lanes: Lane[];
};

const GROUP_ICON: Record<string, React.ReactNode> = {
  抽取: <ExperimentOutlined />,
  预测: <BulbOutlined />,
  写作: <EditOutlined />,
  仿真: <TeamOutlined />,
};

const TIER_COLOR: Record<string, string> = {
  max: "#a855f7",
  plus: "#3b82f6",
  flash: "#10b981",
};

const TIER_LABEL: Record<string, string> = {
  max: "MAX",
  plus: "PLUS",
  flash: "FLASH",
};

export default function SettingsPage() {
  const [bundle, setBundle] = useState<SettingsBundle | null>(null);
  const [draft, setDraft] = useState<{
    default_model_fast: string;
    default_model_strong: string;
    api_key: string;          // empty string = no change; full new key = update
    base_url: string;
    agents: Record<string, Override>;
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [activeAgent, setActiveAgent] = useState<string | null>(null);
  const [keyVisible, setKeyVisible] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; msg: string } | null>(null);

  const fetchAll = async () => {
    setLoading(true);
    try {
      const b: SettingsBundle = await api.settingsGet();
      setBundle(b);
      setDraft({
        default_model_fast: b.settings.default_model_fast,
        default_model_strong: b.settings.default_model_strong,
        api_key: "",                       // never prefill — user types to change
        base_url: b.settings.base_url,
        agents: { ...b.settings.agents },
      });
    } catch (e) {
      message.error("加载失败：" + String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchAll(); }, []);

  const dirty = useMemo(() => {
    if (!bundle || !draft) return false;
    if (draft.default_model_fast !== bundle.settings.default_model_fast) return true;
    if (draft.default_model_strong !== bundle.settings.default_model_strong) return true;
    if (draft.api_key.length > 0) return true;   // user typed a new key
    if (draft.base_url !== bundle.settings.base_url) return true;
    for (const id of Object.keys(draft.agents)) {
      const a = draft.agents[id];
      const b = bundle.settings.agents[id];
      if (a.model !== b.model || a.temperature !== b.temperature
          || a.max_tokens !== b.max_tokens || a.top_p !== b.top_p) return true;
    }
    return false;
  }, [bundle, draft]);

  const save = async () => {
    if (!draft) return;
    setSaving(true);
    try {
      // Strip empty api_key so we don't overwrite the existing one with "".
      const payload: any = { ...draft };
      if (!payload.api_key) delete payload.api_key;
      const updated: SettingsBundle = await api.settingsPut(payload);
      setBundle(updated);
      setDraft({
        default_model_fast: updated.settings.default_model_fast,
        default_model_strong: updated.settings.default_model_strong,
        api_key: "",
        base_url: updated.settings.base_url,
        agents: { ...updated.settings.agents },
      });
      message.success("设置已保存");
    } catch (e) {
      message.error("保存失败：" + String(e));
    } finally {
      setSaving(false);
    }
  };

  const runTest = async () => {
    if (!draft) return;
    setTesting(true);
    setTestResult(null);
    try {
      const r = await api.settingsTestKey({
        api_key: draft.api_key || undefined,    // undefined → use saved key
        base_url: draft.base_url || undefined,
      });
      if (r.ok) {
        setTestResult({ ok: true, msg: `成功 · ${r.model} · 返回："${r.sample}"` });
      } else {
        setTestResult({ ok: false, msg: r.error || "未知错误" });
      }
    } catch (e) {
      setTestResult({ ok: false, msg: String(e) });
    } finally {
      setTesting(false);
    }
  };

  const resetAll = () => {
    Modal.confirm({
      title: "重置所有覆盖？",
      content: "默认模型将回到 qwen3.5-flash，所有 agent 的参数覆盖会被清空。",
      okText: "重置",
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          const updated: SettingsBundle = await api.settingsReset();
          setBundle(updated);
          setDraft({
            default_model_fast: updated.settings.default_model_fast,
            default_model_strong: updated.settings.default_model_strong,
            api_key: "",
            base_url: updated.settings.base_url,
            agents: { ...updated.settings.agents },
          });
          message.success("已重置为默认");
        } catch (e) {
          message.error("重置失败：" + String(e));
        }
      },
    });
  };

  const setLaneDefault = (lane: "fast" | "strong", modelId: string) => {
    if (!draft) return;
    setDraft({
      ...draft,
      [lane === "fast" ? "default_model_fast" : "default_model_strong"]: modelId,
    });
  };

  const setAgentField = (agentId: string, field: keyof Override, value: any) => {
    if (!draft) return;
    setDraft({
      ...draft,
      agents: {
        ...draft.agents,
        [agentId]: { ...draft.agents[agentId], [field]: value },
      },
    });
  };

  const groupedAgents = useMemo(() => {
    if (!bundle) return {};
    return bundle.agents.reduce<Record<string, AgentRow[]>>((acc, a) => {
      (acc[a.group] = acc[a.group] || []).push(a);
      return acc;
    }, {});
  }, [bundle]);

  if (loading || !bundle || !draft) {
    return (
      <div className="container">
        <PageTitle title="设置" />
        <div className="card muted">加载中…</div>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 1240 }}>
      <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
        <PageTitle
          title="模型与参数"
          subtitle="切换 Qwen / DeepSeek 模型 · 21 个 agent 各自温度 / max_tokens / top_p"
        />
        <div style={{ display: "flex", gap: 8 }}>
          <button className="ghost" onClick={resetAll} style={{ padding: "6px 14px" }}>
            <ReloadOutlined /> 重置全部
          </button>
          <button
            disabled={!dirty || saving}
            onClick={save}
            style={{
              padding: "6px 18px",
              background: dirty ? "var(--accent)" : "var(--panel-2)",
              opacity: dirty ? 1 : 0.5,
            }}
          >
            <SaveOutlined /> {saving ? "保存中…" : (dirty ? "保存" : "已保存")}
          </button>
        </div>
      </div>

      {/* ---------- API 凭证 ---------- */}
      <div className="card" style={{ marginBottom: 20 }}>
        <h3 style={{ marginTop: 0, display: "flex", alignItems: "center", gap: 8 }}>
          <KeyOutlined /> API 凭证
          {bundle.settings.api_key_set && (
            <Tag color="green" style={{ fontSize: 11, marginLeft: 4 }}>
              已配置（来源：{bundle.settings.api_key_source === "settings" ? "设置" : "环境变量"}）
            </Tag>
          )}
          {!bundle.settings.api_key_set && bundle.settings.api_key_source === "env" && (
            <Tag color="blue" style={{ fontSize: 11, marginLeft: 4 }}>来自环境变量</Tag>
          )}
          {bundle.settings.api_key_source === "none" && (
            <Tag color="red" style={{ fontSize: 11, marginLeft: 4 }}>未配置</Tag>
          )}
        </h3>
        <p className="muted" style={{ marginTop: -4, fontSize: 12 }}>
          支持 DashScope (Qwen) / OpenAI 兼容端点。设置中的 key 优先于 <code style={{ fontSize: 11 }}>backend/.env</code>。Key 不会以明文返回——只显示首尾 4 位。
        </p>

        <div style={{ marginTop: 14 }}>
          {/* API Key */}
          <label style={{ fontSize: 12, color: "var(--muted)", display: "block", marginBottom: 4 }}>
            API Key
          </label>
          <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 6 }}>
            <input
              type={keyVisible ? "text" : "password"}
              autoComplete="off"
              spellCheck={false}
              value={draft.api_key}
              onChange={(e) => setDraft({ ...draft, api_key: e.target.value })}
              placeholder={bundle.settings.api_key_set
                ? `当前: ${bundle.settings.api_key} （留空则保持不变）`
                : "粘贴 sk-xxx... 来配置"}
              style={{
                flex: 1,
                fontFamily: "monospace",
                fontSize: 13,
                padding: "8px 12px",
                border: "1px solid var(--border)",
                borderRadius: 6,
                background: "var(--panel)",
                color: "inherit",
              }}
            />
            <Tooltip title={keyVisible ? "隐藏" : "显示"}>
              <button
                className="ghost"
                onClick={() => setKeyVisible(!keyVisible)}
                style={{ padding: "8px 12px" }}
                disabled={!draft.api_key}
              >
                {keyVisible ? <EyeInvisibleOutlined /> : <EyeOutlined />}
              </button>
            </Tooltip>
            {draft.api_key && (
              <button
                className="ghost"
                onClick={() => setDraft({ ...draft, api_key: "" })}
                style={{ padding: "8px 12px", fontSize: 12 }}
              >
                清空
              </button>
            )}
          </div>

          {/* Base URL */}
          <label style={{ fontSize: 12, color: "var(--muted)", display: "block", marginTop: 12, marginBottom: 4 }}>
            <LinkOutlined /> Base URL <span style={{ fontSize: 10 }}>（可选，留空使用默认）</span>
          </label>
          <input
            type="text"
            autoComplete="off"
            spellCheck={false}
            value={draft.base_url}
            onChange={(e) => setDraft({ ...draft, base_url: e.target.value })}
            placeholder={bundle.settings.effective_base_url}
            style={{
              width: "100%",
              fontFamily: "monospace",
              fontSize: 12,
              padding: "8px 12px",
              border: "1px solid var(--border)",
              borderRadius: 6,
              background: "var(--panel)",
              color: "inherit",
            }}
          />
          <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>
            当前生效：<code style={{ fontSize: 11 }}>{bundle.settings.effective_base_url}</code>
          </div>

          {/* Test button */}
          <div style={{ display: "flex", gap: 10, alignItems: "center", marginTop: 14 }}>
            <button
              onClick={runTest}
              disabled={testing}
              style={{ padding: "6px 16px", fontSize: 13 }}
            >
              {testing ? "测试中…" : "测试连接"}
            </button>
            {testResult && (
              <div style={{
                fontSize: 12,
                color: testResult.ok ? "var(--good)" : "var(--bad)",
                display: "flex",
                alignItems: "center",
                gap: 4,
              }}>
                {testResult.ok ? <CheckCircleOutlined /> : <CloseCircleOutlined />}
                {testResult.msg}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ---------- 默认模型 lane ---------- */}
      <div className="card" style={{ marginBottom: 20 }}>
        <h3 style={{ marginTop: 0, display: "flex", alignItems: "center", gap: 8 }}>
          <RocketOutlined /> 默认模型（按 lane）
        </h3>
        <p className="muted" style={{ marginTop: -4, fontSize: 12 }}>
          每个 agent 都属于一个 lane（FAST 或 STRONG）。如果不为单个 agent 单独设置 model，就用 lane 的默认。
        </p>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginTop: 12 }}>
          <LaneCard
            label="FAST"
            sub="抽取 / 决策 / 评审 / 短输出"
            icon={<ThunderboltOutlined />}
            value={draft.default_model_fast}
            models={bundle.models}
            onChange={(id) => setLaneDefault("fast", id)}
          />
          <LaneCard
            label="STRONG"
            sub="主创作 / 长输出 / 综合"
            icon={<RocketOutlined />}
            value={draft.default_model_strong}
            models={bundle.models}
            onChange={(id) => setLaneDefault("strong", id)}
          />
        </div>
      </div>

      {/* ---------- Agents per group ---------- */}
      {Object.entries(groupedAgents).map(([group, agents]) => (
        <div className="card" key={group} style={{ marginBottom: 20 }}>
          <h3 style={{ marginTop: 0, display: "flex", alignItems: "center", gap: 8 }}>
            {GROUP_ICON[group] || <DatabaseOutlined />} {group} <span className="muted" style={{ fontSize: 12, fontWeight: "normal" }}>{agents.length} 个 agent</span>
          </h3>

          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(360px, 1fr))",
            gap: 12,
          }}>
            {agents.map((a) => (
              <AgentCard
                key={a.id}
                agent={a}
                draft={draft.agents[a.id]}
                models={bundle.models}
                isActive={activeAgent === a.id}
                onActivate={() => setActiveAgent(activeAgent === a.id ? null : a.id)}
                onChange={(field, value) => setAgentField(a.id, field, value)}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Lane (default model) card
// ---------------------------------------------------------------------------

function LaneCard({
  label, sub, icon, value, models, onChange,
}: {
  label: string;
  sub: string;
  icon: React.ReactNode;
  value: string;
  models: Model[];
  onChange: (id: string) => void;
}) {
  return (
    <div style={{
      border: "1px solid var(--border)",
      borderRadius: 10,
      padding: 14,
      background: "var(--bg)",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 14, marginBottom: 8 }}>
        {icon}
        <strong style={{ color: "var(--accent-2)" }}>{label}</strong>
        <span className="muted" style={{ fontSize: 11 }}>· {sub}</span>
      </div>
      <ModelGrid value={value} models={models} onChange={onChange} compact />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Model grid (cards)
// ---------------------------------------------------------------------------

function ModelGrid({
  value, models, onChange, compact = false,
}: {
  value: string;
  models: Model[];
  onChange: (id: string) => void;
  compact?: boolean;
}) {
  const tiers: ("max" | "plus" | "flash")[] = ["max", "plus", "flash"];
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {tiers.map((tier) => {
        const items = models.filter((m) => m.tier === tier);
        if (items.length === 0) return null;
        return (
          <div key={tier}>
            <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 6, letterSpacing: 1 }}>
              {TIER_LABEL[tier]}
            </div>
            <div style={{
              display: "grid",
              gap: 6,
              gridTemplateColumns: compact ? "repeat(auto-fill, minmax(140px, 1fr))" : "repeat(auto-fill, minmax(200px, 1fr))",
            }}>
              {items.map((m) => {
                const active = m.id === value;
                return (
                  <Tooltip key={m.id} title={
                    <div style={{ fontSize: 11 }}>
                      <div>{m.desc}</div>
                      <div className="muted" style={{ marginTop: 4 }}>
                        ${m.price_in}/M in · ${m.price_out}/M out
                      </div>
                    </div>
                  }>
                    <div
                      onClick={() => onChange(m.id)}
                      style={{
                        cursor: "pointer",
                        padding: compact ? "8px 10px" : "10px 12px",
                        borderRadius: 8,
                        border: active ? `2px solid ${TIER_COLOR[m.tier]}` : "1px solid var(--border)",
                        background: active ? `${TIER_COLOR[m.tier]}1A` : "var(--panel)",
                        position: "relative",
                        transition: "all 0.15s",
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 4 }}>
                        <span style={{
                          fontFamily: "monospace",
                          fontSize: compact ? 11 : 12,
                          fontWeight: active ? 600 : 400,
                          color: active ? TIER_COLOR[m.tier] : "var(--text)",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}>
                          {m.id}
                        </span>
                        {active && <CheckCircleFilled style={{ color: TIER_COLOR[m.tier], fontSize: 12 }} />}
                      </div>
                      {!compact && (
                        <div style={{ fontSize: 10, color: "var(--muted)", marginTop: 3 }}>
                          {m.tag} · ${m.price_in}/${m.price_out}
                        </div>
                      )}
                    </div>
                  </Tooltip>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Per-agent card
// ---------------------------------------------------------------------------

function AgentCard({
  agent, draft, models, isActive, onActivate, onChange,
}: {
  agent: AgentRow;
  draft: Override;
  models: Model[];
  isActive: boolean;
  onActivate: () => void;
  onChange: (field: keyof Override, value: any) => void;
}) {
  const hasOverride =
    draft.model !== null || draft.temperature !== null ||
    draft.max_tokens !== null || draft.top_p !== null;

  const effective = {
    model: draft.model || agent.defaults.model,
    temperature: draft.temperature ?? agent.defaults.temperature,
    max_tokens: draft.max_tokens ?? agent.defaults.max_tokens,
    top_p: draft.top_p ?? agent.defaults.top_p,
  };

  return (
    <div style={{
      border: hasOverride ? "1.5px solid var(--accent)" : "1px solid var(--border)",
      borderRadius: 10,
      padding: 12,
      background: "var(--bg)",
      transition: "all 0.15s",
    }}>
      <div
        onClick={onActivate}
        style={{ cursor: "pointer", display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 8 }}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <code style={{
              fontSize: 12,
              fontWeight: 600,
              color: hasOverride ? "var(--accent)" : "var(--accent-2)",
            }}>
              {agent.id}
            </code>
            <Tag color={agent.lane === "strong" ? "purple" : "green"} style={{ fontSize: 10, lineHeight: "16px", margin: 0 }}>
              {agent.lane.toUpperCase()}
            </Tag>
            {hasOverride && (
              <Tag color="orange" style={{ fontSize: 10, lineHeight: "16px", margin: 0 }}>已覆盖</Tag>
            )}
          </div>
          <div className="muted" style={{ fontSize: 11, marginTop: 4 }}>{agent.desc}</div>
          <div style={{ fontSize: 11, marginTop: 6, color: "var(--muted)" }}>
            <span style={{ fontFamily: "monospace" }}>{effective.model}</span>
            <span style={{ marginLeft: 10 }}>T={effective.temperature}</span>
            <span style={{ marginLeft: 10 }}>max={effective.max_tokens}</span>
            {effective.top_p != null && <span style={{ marginLeft: 10 }}>top_p={effective.top_p}</span>}
          </div>
        </div>
        <span style={{ color: "var(--muted)", fontSize: 12, paddingTop: 2 }}>
          {isActive ? "▾" : "▸"}
        </span>
      </div>

      {isActive && (
        <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px dashed var(--border)" }}>
          {/* Model override */}
          <div style={{ marginBottom: 14 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
              <label style={{ fontSize: 12, color: "var(--muted)" }}>模型</label>
              <button
                className="ghost"
                onClick={() => onChange("model", null)}
                disabled={draft.model === null}
                style={{ padding: "2px 8px", fontSize: 10 }}
              >
                跟随 lane 默认
              </button>
            </div>
            <ModelGrid
              value={draft.model || effective.model}
              models={models}
              onChange={(id) => onChange("model", id)}
              compact
            />
          </div>

          {/* Temperature */}
          <ParamRow
            label="Temperature"
            defaultValue={agent.defaults.temperature}
            value={draft.temperature}
            min={0}
            max={2}
            step={0.05}
            onChange={(v) => onChange("temperature", v)}
            onReset={() => onChange("temperature", null)}
          />

          {/* Max tokens */}
          <ParamRow
            label="Max tokens"
            defaultValue={agent.defaults.max_tokens}
            value={draft.max_tokens}
            min={256}
            max={32000}
            step={256}
            onChange={(v) => onChange("max_tokens", v)}
            onReset={() => onChange("max_tokens", null)}
            integer
          />

          {/* Top-p (allow null) */}
          <ParamRow
            label="Top-p"
            defaultValue={agent.defaults.top_p ?? null}
            value={draft.top_p}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => onChange("top_p", v)}
            onReset={() => onChange("top_p", null)}
            allowNull
          />
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Param slider row
// ---------------------------------------------------------------------------

function ParamRow({
  label, defaultValue, value, min, max, step, onChange, onReset, integer = false, allowNull = false,
}: {
  label: string;
  defaultValue: number | null;
  value: number | null;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
  onReset: () => void;
  integer?: boolean;
  allowNull?: boolean;
}) {
  const overridden = value !== null;
  const effective = value ?? defaultValue;

  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
        <label style={{ fontSize: 12, color: "var(--muted)" }}>
          {label}
          {!overridden && (
            <span style={{ marginLeft: 6, fontSize: 10 }}>
              · 默认 <code style={{ fontSize: 10 }}>{defaultValue ?? "—"}</code>
            </span>
          )}
        </label>
        <button
          className="ghost"
          onClick={onReset}
          disabled={!overridden}
          style={{ padding: "2px 8px", fontSize: 10 }}
        >
          重置
        </button>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <Slider
          min={min}
          max={max}
          step={step}
          value={effective ?? min}
          disabled={effective === null}
          onChange={(v) => onChange(typeof v === "number" ? v : Number(v))}
          style={{ flex: 1 }}
        />
        <InputNumber
          min={min}
          max={max}
          step={step}
          value={effective}
          onChange={(v) => {
            if (v === null && allowNull) onReset();
            else if (v != null) onChange(integer ? Math.round(Number(v)) : Number(v));
          }}
          size="small"
          style={{ width: 92 }}
        />
      </div>
    </div>
  );
}
