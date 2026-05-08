"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Drawer, Tag, Tooltip } from "antd";
import { TeamOutlined, MessageOutlined } from "@ant-design/icons";
import { api } from "@/lib/api";
import PageTitle from "@/components/PageTitle";

const ACTION_KIND_COLOR: Record<string, string> = {
  speak: "var(--c-story)",
  act: "var(--c-foreshadow)",
  move: "var(--c-character)",
  observe: "var(--muted)",
  reveal: "var(--bad)",
  decide: "var(--c-mystery)",
  wait: "var(--border)",
};
const ACTION_KIND_LABEL: Record<string, string> = {
  speak: "说", act: "做", move: "走", observe: "察",
  reveal: "揭", decide: "断", wait: "待",
};

const ROLE_COLOR: Record<string, string> = {
  protagonist: "#ef4444", antagonist: "#a855f7",
  ally: "#3b82f6", supporting: "#f59e0b", minor: "#9ca3af",
};

export default function SimPage() {
  const [profiles, setProfiles] = useState<any[]>([]);
  const [history, setHistory] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [busySince, setBusySince] = useState<number | null>(null);
  const [, setTick] = useState(0);
  const [msg, setMsg] = useState("");
  const [run, setRun] = useState<any | null>(null);
  const [drawerProfile, setDrawerProfile] = useState<any | null>(null);

  // form
  const [afterCh, setAfterCh] = useState(1472);
  const [nRounds, setNRounds] = useState(3);
  const [nCharacters, setNCharacters] = useState(5);
  const [focus, setFocus] = useState<number[]>([]);
  const [hints, setHints] = useState("");
  const [profilesBusy, setProfilesBusy] = useState(false);

  const reload = async () => {
    setProfiles(await api.profilesList().catch(() => []));
    setHistory(await api.simulationsList().catch(() => []));
  };
  useEffect(() => { reload(); }, []);

  useEffect(() => {
    if (!busy) return;
    const t = setInterval(() => setTick((x) => x + 1), 1000);
    return () => clearInterval(t);
  }, [busy]);

  const elapsed = busy && busySince ? Math.floor((Date.now() - busySince) / 1000) : 0;

  const rebuildProfiles = async () => {
    setProfilesBusy(true);
    setMsg("");
    try {
      const r = await api.profilesRebuild({ top_n: 20, after_chapter: afterCh });
      setMsg(`✅ 角色档案：${r.built}/${r.total_targeted} 成功 · $${r.cost_usd.toFixed(4)}`);
      reload();
    } catch (e: any) {
      setMsg(String(e));
    } finally {
      setProfilesBusy(false);
    }
  };

  const triggerSim = async () => {
    setBusy(true);
    setBusySince(Date.now());
    setMsg("");
    setRun(null);
    try {
      const r = await api.simulate({
        after_chapter: afterCh,
        n_rounds: nRounds,
        n_characters: nCharacters,
        focus_characters: focus.length > 0 ? focus : undefined,
        user_hints: hints,
      });
      setRun(r);
      setMsg(`✅ 仿真完成 · ${r.cost_usd ? `$${r.cost_usd.toFixed(4)}` : ""}`);
      reload();
    } catch (e: any) {
      setMsg(String(e));
    } finally {
      setBusy(false);
      setBusySince(null);
    }
  };

  const loadHistory = async (id: number) => {
    const r = await api.simulationGet(id);
    setRun(r);
  };

  const toggleFocus = (id: number) => {
    setFocus((cur) => cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]);
  };

  const profileById: Record<number, any> = useMemo(() => {
    const m: Record<number, any> = {};
    for (const p of profiles) m[p.entity_id] = p;
    return m;
  }, [profiles]);

  return (
    <>
      <PageTitle title="角色仿真"
        subtitle="多角色独立决策 · 多轮迭代 · ReportAgent 综合 → 涌现性章节" />

      <div className="card">
        <h2>触发仿真</h2>
        <div className="row" style={{ alignItems: "center", flexWrap: "wrap" }}>
          <label>从第<input type="number" value={afterCh} onChange={(e) => setAfterCh(+e.target.value)} style={{ width: 80, marginLeft: 4, marginRight: 4 }} />章后</label>
          <label>角色数<input type="number" value={nCharacters} onChange={(e) => setNCharacters(+e.target.value)} min={2} max={8} style={{ width: 50, marginLeft: 4 }} /></label>
          <label>轮数<input type="number" value={nRounds} onChange={(e) => setNRounds(+e.target.value)} min={1} max={8} style={{ width: 50, marginLeft: 4 }} /></label>
          <span className="muted" style={{ fontSize: 12 }}>
            ≈ {nRounds * nCharacters + 1} 次 LLM · ${(0.003 * (nRounds * nCharacters + 1)).toFixed(3)} · {Math.ceil(nRounds * 25 + 30)}秒
          </span>
        </div>
        <textarea value={hints} onChange={(e) => setHints(e.target.value)} rows={2}
          placeholder="（可选）创作偏好/导演备注…"
          style={{ marginTop: 8, width: "100%", background: "var(--panel-2)", color: "var(--text)",
                   border: "1px solid var(--border)", borderRadius: 6, padding: 8, fontFamily: "inherit", fontSize: 13 }} />
        <div style={{ marginTop: 10, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <button onClick={triggerSim} disabled={busy || profiles.length === 0}>
            {busy ? `仿真中… ${elapsed}s` : "运行仿真"}
          </button>
          <button onClick={rebuildProfiles} disabled={profilesBusy} className="ghost">
            {profilesBusy ? "构建档案中…" : `${profiles.length === 0 ? "🪄 先构建" : "重建"} top-20 档案`}
          </button>
          {profiles.length === 0 && <span className="muted" style={{ fontSize: 12 }}>没有档案就无法仿真</span>}
        </div>
        {msg && <p style={{ marginTop: 8, fontSize: 12, color: msg.startsWith("✅") ? "var(--good)" : "var(--bad)" }}>{msg}</p>}
      </div>

      {/* 角色档案选择 */}
      {profiles.length > 0 && (
        <div className="card">
          <h3>选择参演角色（不选则按重要度自动选 top-{nCharacters}）</h3>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {profiles.slice(0, 20).map((p) => {
              const active = focus.includes(p.entity_id);
              const color = ROLE_COLOR[p.role || "minor"];
              return (
                <button key={p.entity_id}
                  onClick={() => toggleFocus(p.entity_id)}
                  className={active ? "" : "ghost"}
                  style={{
                    padding: "4px 10px", fontSize: 12,
                    borderColor: active ? color : "var(--border)",
                    background: active ? `${color}25` : undefined,
                    color: active ? color : "var(--text)",
                  }}>
                  {p.name}
                  {p.role && <span style={{ marginLeft: 4, opacity: 0.7, fontSize: 10 }}>· {p.role}</span>}
                </button>
              );
            })}
          </div>
          <p className="muted" style={{ fontSize: 11, marginTop: 6, marginBottom: 0 }}>
            点击切换。已选 {focus.length} 人。
          </p>
        </div>
      )}

      {/* 当前运行 */}
      {run && (
        <div className="row" style={{ alignItems: "stretch", gap: 14 }}>
          {/* 左：行动流 */}
          <div className="card" style={{ flex: 2, marginBottom: 0, minWidth: 0 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", flexWrap: "wrap" }}>
              <h2 style={{ margin: 0 }}>仿真 #{run.id} · 第 {run.after_chapter}+ 章</h2>
              <span className="muted" style={{ fontSize: 12 }}>
                {run.cost_usd ? `$${run.cost_usd.toFixed(4)}` : ""} · {run.status}
              </span>
            </div>
            <div style={{ marginTop: 10, display: "grid", gap: 16 }}>
              {(run.rounds_json || run.rounds || []).map((rd: any) => (
                <div key={rd.round}>
                  <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 6, fontWeight: 600 }}>
                    第 {rd.round} 轮
                  </div>
                  <div style={{ display: "grid", gap: 8 }}>
                    {(rd.actions || []).map((a: any, i: number) => {
                      const color = ACTION_KIND_COLOR[a.kind] || "var(--muted)";
                      return (
                        <div key={i} style={{
                          background: "var(--panel-2)", borderRadius: 6, padding: 10,
                          borderLeft: `3px solid ${color}`,
                        }}>
                          <div style={{ display: "flex", gap: 6, alignItems: "baseline", marginBottom: 4 }}>
                            <span className="tag" style={{ background: `${color}25`, color, fontWeight: 600 }}>
                              {ACTION_KIND_LABEL[a.kind] || a.kind}
                            </span>
                            <strong style={{ fontSize: 14 }}>{a.character}</strong>
                            {a.target_name && <span className="muted" style={{ fontSize: 11 }}>→ {a.target_name}</span>}
                            {a.emotional_state && <span className="muted" style={{ fontSize: 11, fontStyle: "italic" }}>· {a.emotional_state}</span>}
                          </div>
                          <div className="prose-cn" style={{ fontSize: 13, lineHeight: 1.7, marginBottom: 4 }}>
                            {a.content}
                          </div>
                          {a.reasoning && (
                            <div className="muted" style={{ fontSize: 11, fontStyle: "italic" }}>
                              内心：{a.reasoning}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>

            {run.final_text && (
              <>
                <h3 style={{ marginTop: 20 }}>📖 综合章节</h3>
                <pre style={{
                  whiteSpace: "pre-wrap",
                  fontFamily: 'ui-serif, "PingFang SC", serif',
                  fontSize: 14, lineHeight: 1.85,
                  background: "var(--panel-2)", padding: 16, borderRadius: 6,
                  margin: 0,
                }}>{run.final_text}</pre>
              </>
            )}
          </div>

          {/* 右：参演档案 */}
          <div className="card" style={{ flex: "0 0 280px", marginBottom: 0, alignSelf: "flex-start" }}>
            <h3>参演角色</h3>
            <div style={{ display: "grid", gap: 8 }}>
              {(run.cast_names || run.cast || []).map((name: string) => {
                const p = profiles.find((x) => x.name === name);
                if (!p) return <div key={name} className="muted">{name}</div>;
                const color = ROLE_COLOR[p.role || "minor"];
                return (
                  <div key={name} onClick={() => setDrawerProfile(p)}
                    style={{ background: "var(--panel-2)", padding: 10, borderRadius: 6,
                             borderLeft: `3px solid ${color}`, cursor: "pointer" }}>
                    <div style={{ fontSize: 14, fontWeight: 600 }}>{name}</div>
                    <div className="muted" style={{ fontSize: 11 }}>{p.role}</div>
                    <Link href={`/character/${p.entity_id}`}
                      style={{ fontSize: 11, marginTop: 4, display: "inline-flex", alignItems: "center", gap: 4 }}>
                      <MessageOutlined /> 找他对话
                    </Link>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* 历史 */}
      <div className="card">
        <h2>历史仿真</h2>
        <table>
          <thead><tr><th>id</th><th>章节</th><th>角色×轮</th><th>$</th><th>状态</th><th>时间</th><th></th></tr></thead>
          <tbody>
            {history.map((h) => (
              <tr key={h.id}>
                <td>{h.id}</td>
                <td>{h.after_chapter}</td>
                <td>{h.n_characters}×{h.n_rounds}</td>
                <td>${h.cost_usd?.toFixed(4)}</td>
                <td>{h.status}</td>
                <td className="muted">{h.created_at?.replace("T", " ").slice(0, 19)}</td>
                <td><button onClick={() => loadHistory(h.id)} className="ghost" style={{ padding: "4px 10px", fontSize: 12 }}>查看</button></td>
              </tr>
            ))}
            {history.length === 0 && <tr><td colSpan={7} className="muted">暂无</td></tr>}
          </tbody>
        </table>
      </div>

      {/* 角色档案 Drawer */}
      <Drawer title={drawerProfile?.name} placement="right" width={500}
        open={!!drawerProfile} onClose={() => setDrawerProfile(null)} mask={false}>
        {drawerProfile && (
          <div className="prose-cn">
            <Tag color={ROLE_COLOR[drawerProfile.role || "minor"]?.startsWith("#") ? undefined : "default"}
              style={{ background: ROLE_COLOR[drawerProfile.role || "minor"], color: "#fff", border: 0 }}>
              {drawerProfile.role}
            </Tag>
            {drawerProfile.bio && <p style={{ marginTop: 12 }}>{drawerProfile.bio}</p>}
            {drawerProfile.desires?.length > 0 && (
              <>
                <h4 style={{ borderLeft: "3px solid var(--c-story)", paddingLeft: 8 }}>欲望</h4>
                <ul>{drawerProfile.desires.map((d: string, i: number) => <li key={i}>{d}</li>)}</ul>
              </>
            )}
            {drawerProfile.fears?.length > 0 && (
              <>
                <h4 style={{ borderLeft: "3px solid var(--bad)", paddingLeft: 8 }}>恐惧</h4>
                <ul>{drawerProfile.fears.map((d: string, i: number) => <li key={i}>{d}</li>)}</ul>
              </>
            )}
            {drawerProfile.voice_style && (
              <>
                <h4 style={{ borderLeft: "3px solid var(--c-foreshadow)", paddingLeft: 8 }}>语言风格</h4>
                <p style={{ fontStyle: "italic" }}>{drawerProfile.voice_style}</p>
              </>
            )}
            <Link href={`/character/${drawerProfile.entity_id}`} className="btn"
              style={{ marginTop: 16, display: "inline-flex", alignItems: "center", gap: 6 }}>
              <MessageOutlined /> 找他对话
            </Link>
          </div>
        )}
      </Drawer>
    </>
  );
}
