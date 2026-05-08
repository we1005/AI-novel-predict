"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import PageTitle from "@/components/PageTitle";

export default function MonitorPage() {
  const [s, setS] = useState<any | null>(null);
  const [recent, setRecent] = useState<any[]>([]);
  const [hours, setHours] = useState(168);

  useEffect(() => {
    const load = () => {
      api.monitorSummary(hours).then(setS);
      api.monitorRecent(50).then(setRecent);
    };
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [hours]);

  return (
    <>
      <PageTitle title="LLM 调用监控" subtitle="Token / 缓存 / 各 agent 占比 / 累计成本" />

      <div className="card">
        <div className="row" style={{ alignItems: "center" }}>
          <span className="muted">时间窗</span>
          <select value={hours} onChange={(e) => setHours(+e.target.value)}>
            <option value={1}>1 小时</option>
            <option value={24}>1 天</option>
            <option value={168}>1 周</option>
            <option value={720}>1 月</option>
          </select>
        </div>
      </div>

      {s && (
        <div className="row">
          <Metric k="调用次数" v={s.calls} />
          <Metric k="总花费 (USD)" v={`$${s.cost_usd}`} />
          <Metric k="输入 token" v={s.input_tokens.toLocaleString()} />
          <Metric k="输出 token" v={s.output_tokens.toLocaleString()} />
          <Metric k="缓存写" v={s.cache_creation_tokens.toLocaleString()} />
          <Metric k="缓存读" v={s.cache_read_tokens.toLocaleString()} />
          <Metric k="缓存命中率" v={`${(s.cache_hit_ratio * 100).toFixed(1)}%`} />
        </div>
      )}

      <div className="card">
        <h2>各 agent 占比</h2>
        <table>
          <thead><tr><th>agent</th><th>调用</th><th>$</th><th>缓存读 token</th><th>输入 token</th></tr></thead>
          <tbody>
            {(s?.per_agent ?? []).map((a: any) => (
              <tr key={a.agent}>
                <td>{a.agent}</td>
                <td>{a.calls}</td>
                <td>${a.cost_usd}</td>
                <td>{a.cache_read_tokens.toLocaleString()}</td>
                <td>{a.input_tokens.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h2>最近 50 次调用</h2>
        <table>
          <thead><tr><th>时间</th><th>agent</th><th>model</th><th>in</th><th>out</th><th>cache_w</th><th>cache_r</th><th>ms</th><th>$</th></tr></thead>
          <tbody>
            {recent.map((r) => (
              <tr key={r.id}>
                <td className="muted">{r.created_at?.replace("T", " ").slice(11, 19)}</td>
                <td>{r.agent}</td>
                <td className="muted">{r.model}</td>
                <td>{r.input_tokens}</td>
                <td>{r.output_tokens}</td>
                <td>{r.cache_creation_tokens}</td>
                <td>{r.cache_read_tokens}</td>
                <td>{r.elapsed_ms}</td>
                <td>${r.cost_usd?.toFixed(4)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function Metric({ k, v }: { k: string; v: any }) {
  return (
    <div className="metric">
      <div className="k">{k}</div>
      <div className="v">{v}</div>
    </div>
  );
}
