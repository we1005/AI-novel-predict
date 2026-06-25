"use client";

import { useEffect, useRef, useState } from "react";
import { Tag, Tooltip, Modal, message } from "antd";
import { BookOutlined, FileTextOutlined, RedoOutlined, WarningOutlined, CheckOutlined } from "@ant-design/icons";
import Link from "next/link";
import { api } from "@/lib/api";
import PageTitle from "@/components/PageTitle";

type ActiveBook = {
  slug: string;
  title: string;
  has_corpus: boolean;
  corpus_bytes: number;
};

export default function IngestPage() {
  const [book, setBook] = useState<ActiveBook | null>(null);
  const [count, setCount] = useState<number | null>(null);
  const [batches, setBatches] = useState<any[]>([]);
  const [start, setStart] = useState(1);
  const [end, setEnd] = useState(51);
  const [batchSize, setBatchSize] = useState(50);
  const [workers, setWorkers] = useState(2);
  const [busy, setBusy] = useState(false);
  const [splitResult, setSplitResult] = useState<string>("");
  const [extractAllResult, setExtractAllResult] = useState<string>("");
  const [err, setErr] = useState("");

  const [coverage, setCoverage] = useState<{ total: number; covered: number; missing_ranges: [number, number][] } | null>(null);
  const [recommend, setRecommend] = useState<{ batch_size: number; workers: number; median_chars: number; total_chapters: number; est_batches?: number; rationale: string } | null>(null);
  const appliedBook = useRef<string | null>(null);

  const refresh = async () => {
    try {
      const c = await api.chapterCount();
      setCount(c.total);
      const b = await api.batches();
      setBatches(b);
      const bk = await api.booksList();
      const active = bk.books.find((x: any) => x.active) || null;
      setBook(active);
      try {
        const cov = await api.extractionCoverage();
        setCoverage(cov);
      } catch { /* noop */ }
    } catch (e: any) {
      setErr(String(e));
    }
  };

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, []);

  // 按体量推荐「每批/并发」默认值,每本书自动带入一次(用户改过就不再覆盖)。
  useEffect(() => {
    if (!book?.slug || !count || count <= 0) return;
    if (appliedBook.current === book.slug) return;
    api.recommendBatch().then((r) => {
      setRecommend(r);
      setBatchSize(r.batch_size);
      setWorkers(r.workers);
      appliedBook.current = book.slug;
    }).catch(() => {});
  }, [book?.slug, count]);

  const split = async () => {
    setBusy(true); setErr(""); setSplitResult("");
    try {
      const r = await api.splitCorpus();   // no path — uses active book's corpus
      setSplitResult(`已切分 ${r.chapters} 章 · 共 ${r.total_chars.toLocaleString()} 字`);
      await refresh();
    } catch (e: any) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  const extract = async () => {
    setBusy(true); setErr("");
    try { await api.startExtract(start, end); await refresh(); }
    catch (e: any) { setErr(String(e)); }
    finally { setBusy(false); }
  };

  const extractAll = async () => {
    setBusy(true); setErr(""); setExtractAllResult("");
    try {
      const r = await api.startExtractAll(batchSize, workers);
      if (r.msg) {
        setExtractAllResult(r.msg);
      } else {
        const parts = [
          `本次排队 ${r.queued} 批（最多 ${r.workers} 并发）`,
          r.skipped_done > 0 ? `${r.skipped_done} 已完成跳过` : "",
          r.skipped_running > 0 ? `⚠️ ${r.skipped_running} 与运行中批次重叠，已自动跳过` : "",
        ].filter(Boolean).join("，");
        setExtractAllResult(parts + "。");
      }
      await refresh();
    } catch (e: any) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  const retryBatch = (b: any) => {
    Modal.confirm({
      title: `重试批次 #${b.id}`,
      width: 500,
      content: (
        <div style={{ fontSize: 13, lineHeight: 1.7 }}>
          <p>将严格使用此批次原始范围 <code style={{ background: "var(--bg)", padding: "2px 8px", borderRadius: 4 }}>章 {b.chapter_start}–{b.chapter_end - 1}</code> 重新抽取——不会偏移。</p>
          <p style={{ color: "var(--muted)", fontSize: 12 }}>
            后端会先检查这段范围是否已被其他 done 批次覆盖：
          </p>
          <ul style={{ fontSize: 12, color: "var(--muted)", paddingLeft: 20 }}>
            <li><b>已覆盖</b> → 直接标"superseded"，不调 LLM、不花钱</li>
            <li><b>有未覆盖章节</b> → 后台重新跑 6-agent 抽取</li>
          </ul>
          {b.error && (
            <details style={{ marginTop: 8, fontSize: 11 }}>
              <summary style={{ cursor: "pointer", color: "var(--muted)" }}>原失败原因</summary>
              <pre style={{ marginTop: 6, padding: 8, background: "var(--bg)", borderRadius: 4, fontSize: 11, overflow: "auto", maxHeight: 200 }}>
                {b.error}
              </pre>
            </details>
          )}
        </div>
      ),
      okText: "重试",
      onOk: async () => {
        try {
          const r = await api.retryBatch(b.id);
          if (r.action === "superseded") {
            message.success(
              `[${r.range[0]},${r.range[1]}) 已被其他批次完整覆盖，标记为已覆盖（未实际重跑，0 token）`
            );
          } else {
            message.success(
              `已加入后台队列：[${r.range[0]},${r.range[1]})，其中 ${r.gap_total} 章尚未被覆盖`
            );
          }
          await refresh();
        } catch (e: any) {
          message.error("重试失败：" + String(e));
        }
      },
    });
  };

  const cleanupStuck = async () => {
    setBusy(true); setErr("");
    try {
      const r = await api.cleanupStuckBatches(30);
      setExtractAllResult(
        r.cleaned > 0
          ? `已把 ${r.cleaned} 个 >30 分钟的 running 批次标记为失败。可重新触发抽取。`
          : "没有超过 30 分钟仍在 running 的批次"
      );
      await refresh();
    } catch (e: any) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  // Live progress. IMPORTANT: drive the bar from *coverage* (chapters actually
  // extracted ÷ total chapters), NOT from done-batch-count ÷ an estimate. The
  // estimate (totalChapters / current batchSize) can disagree with the real
  // batches (which may have been created at a different batch size), producing
  // nonsense like "已完成 5 / 4 · 125%". Coverage is batch-size-independent.
  const totalChapters = count || 0;
  // Batches the next "一键抽取全书" run would create at the chosen size — used
  // only for the planning hint, never for progress.
  const plannedBatches = totalChapters > 0 ? Math.ceil(totalChapters / batchSize) : 0;
  const doneBatches = batches.filter((b) => b.status === "done").length;
  const runningBatches = batches.filter((b) => b.status === "running").length;
  const failedBatches = batches.filter((b) => b.status === "failed").length;
  const supersededBatches = batches.filter((b) => b.status === "superseded").length;
  // Coverage-based progress (source of truth).
  const covTotal = coverage?.total ?? totalChapters;
  const covDone = coverage?.covered ?? 0;
  const pct = covTotal > 0 ? Math.min(100, Math.round((covDone / covTotal) * 100)) : 0;

  const fmtBytes = (n: number) => {
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / 1024 / 1024).toFixed(1)} MB`;
  };

  return (
    <>
      <PageTitle title="语料处理" subtitle="编码检测 → 章节切分 → 多 Agent 抽取（实体 / 伏笔 / 状态 / 剧情 / 世界 / 疑点）" />

      {/* ---------- Active book bar ---------- */}
      {book ? (
        <div className="card" style={{
          display: "flex", alignItems: "center", gap: 12,
          padding: "12px 18px", marginBottom: 16,
          borderLeft: "4px solid var(--accent)",
        }}>
          <BookOutlined style={{ color: "var(--accent)", fontSize: 18 }} />
          <div style={{ flex: 1 }}>
            <div style={{ fontFamily: "var(--decorative)", fontSize: 18, color: "var(--accent-2)", letterSpacing: 1 }}>
              《{book.title}》
            </div>
            <div className="muted" style={{ fontSize: 11 }}>
              当前活跃书 · 操作只影响这本书
            </div>
          </div>
          {book.has_corpus && (
            <Tag color="green" style={{ margin: 0 }}>
              <FileTextOutlined /> {fmtBytes(book.corpus_bytes)}
            </Tag>
          )}
          <Link href="/library" style={{ fontSize: 12, color: "var(--accent)" }}>
            切换 →
          </Link>
        </div>
      ) : (
        <div className="card muted" style={{ marginBottom: 16 }}>
          没有活跃书。先到 <Link href="/library" style={{ color: "var(--accent)" }}>书架</Link> 导入一本。
        </div>
      )}

      <div className="card">
        <h2 style={{ marginTop: 0 }}>1. 切分章节</h2>
        <p className="muted">
          按"第N章 …"正则切分入 SQLite + FTS5。语料路径自动按当前活跃书定位。
          <br />
          {book && (
            <code style={{ fontSize: 11, background: "var(--bg)", padding: "2px 8px", borderRadius: 4 }}>
              data/books/{book.slug}/corpus.txt
            </code>
          )}
        </p>
        <div className="row" style={{ alignItems: "center", marginTop: 12 }}>
          <button onClick={split} disabled={busy || !book?.has_corpus}>
            {busy ? "切分中…" : "切分当前书"}
          </button>
          <span style={{ marginLeft: 16 }}>
            当前总章节：<b style={{ color: count ? "var(--accent)" : "var(--muted)" }}>{count ?? "—"}</b>
          </span>
          {splitResult && (
            <span style={{ color: "var(--good)", fontSize: 12, marginLeft: 16 }}>
              {splitResult}
            </span>
          )}
        </div>
      </div>

      <div className="card">
        <h2 style={{ marginTop: 0 }}>2. 抽取</h2>
        <p className="muted">
          6 个 agent 顺序跑（实体 / 伏笔 / 状态 / 剧情 / 世界规则 / 疑点），写入当前书的记忆库。
        </p>

        {/* ---- Progress bar (coverage-based, never exceeds 100%) ---- */}
        {totalChapters > 0 && (
          <div style={{ marginBottom: 14 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4, flexWrap: "wrap" }}>
              <span className="muted" style={{ fontSize: 12 }}>已抽取</span>
              <strong style={{ color: "var(--good)" }}>{covDone}</strong>
              <span className="muted">/</span>
              <strong>{covTotal}</strong>
              <span className="muted" style={{ fontSize: 12 }}>章</span>
              {/* Batch tallies are secondary, shown as raw counts (no ratio). */}
              <span className="muted" style={{ fontSize: 12, marginLeft: 6 }}>
                · 批次：完成 <strong style={{ color: "var(--good)" }}>{doneBatches}</strong>
                {runningBatches > 0 && <> · 运行中 <strong style={{ color: "var(--accent)" }}>{runningBatches}</strong></>}
                {failedBatches > 0 && <span style={{ color: "var(--bad)" }}> · 失败 {failedBatches}</span>}
                {supersededBatches > 0 && <> · 已覆盖 {supersededBatches}</>}
              </span>
              {runningBatches > workers && (
                <Tooltip title="运行中批次数超过你的并发设置 → 多半是上次抽取中断留下的僵尸批次。点此把 >30 分钟仍 running 的标为失败，即可重新抽取。">
                  <button
                    className="ghost"
                    onClick={cleanupStuck}
                    disabled={busy}
                    style={{ padding: "2px 8px", fontSize: 11 }}
                  >
                    清理僵尸批次（{runningBatches}）
                  </button>
                </Tooltip>
              )}
              <span className="muted" style={{ fontSize: 11, marginLeft: "auto" }}>
                {pct}%
              </span>
            </div>
            <div style={{
              width: "100%", height: 8, borderRadius: 4,
              background: "var(--bg)", overflow: "hidden", border: "1px solid var(--border)",
            }}>
              <div style={{
                width: `${pct}%`,
                height: "100%",
                background: "linear-gradient(90deg, var(--accent), var(--accent-2))",
                transition: "width 0.4s",
              }} />
            </div>
          </div>
        )}

        {/* ---- Big "extract all" button ---- */}
        <div className="row" style={{ alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <button
            onClick={extractAll}
            disabled={busy || !count}
            style={{
              padding: "10px 24px",
              fontSize: 14,
              fontWeight: 600,
              background: "var(--accent)",
            }}
          >
            ⚡ 一键抽取全书
          </button>
          <label style={{ fontSize: 12, color: "var(--muted)" }}>
            每批
            <input
              type="number"
              value={batchSize}
              onChange={(e) => setBatchSize(Math.max(1, +e.target.value || 1))}
              style={{ width: 70, marginLeft: 4, marginRight: 2 }}
            />
            章
          </label>
          <label style={{ fontSize: 12, color: "var(--muted)" }}>
            并发
            <input
              type="number"
              value={workers}
              onChange={(e) => setWorkers(Math.max(1, Math.min(8, +e.target.value || 2)))}
              style={{ width: 50, marginLeft: 4 }}
            />
          </label>
          <span className="muted" style={{ fontSize: 11 }}>
            {plannedBatches > 0
              ? `每批 ${batchSize} 章 → 约 ${plannedBatches} 批，已覆盖章节会跳过`
              : "需先切分章节"}
          </span>
        </div>
        {recommend && (
          <div className="muted" style={{ fontSize: 11, marginTop: 6, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <span>💡 按体量推荐 每批 <b style={{ color: "var(--accent-2)" }}>{recommend.batch_size}</b> 章 · 并发 <b style={{ color: "var(--accent-2)" }}>{recommend.workers}</b>（{recommend.rationale}）</span>
            {(batchSize !== recommend.batch_size || workers !== recommend.workers) && (
              <button onClick={() => { setBatchSize(recommend.batch_size); setWorkers(recommend.workers); }}
                className="ghost" style={{ padding: "2px 8px", fontSize: 11 }}>采用推荐</button>
            )}
          </div>
        )}
        {extractAllResult && (
          <div style={{ marginTop: 8, fontSize: 12, color: "var(--good)" }}>{extractAllResult}</div>
        )}

        {/* ---- Manual single-batch (collapsed) ---- */}
        <details style={{ marginTop: 14 }}>
          <summary style={{ cursor: "pointer", fontSize: 12, color: "var(--muted)" }}>
            手动单批（高级）
          </summary>
          <div className="row" style={{ alignItems: "center", marginTop: 8 }}>
            <label>start <input type="number" value={start} onChange={(e) => setStart(+e.target.value)} style={{ width: 90 }} /></label>
            <label>end <input type="number" value={end} onChange={(e) => setEnd(+e.target.value)} style={{ width: 90 }} /></label>
            <button onClick={extract} disabled={busy || !count} className="ghost">触发单批</button>
          </div>
        </details>
      </div>

      <div className="card">
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
          <h2 style={{ marginTop: 0, marginBottom: 0 }}>批次进度</h2>

          {/* ---- Coverage integrity banner ---- */}
          {coverage && coverage.total > 0 && (
            <div style={{
              fontSize: 12,
              padding: "6px 14px",
              borderRadius: 6,
              background: coverage.missing_ranges.length === 0
                ? "rgba(82, 196, 26, 0.1)"
                : "rgba(250, 173, 20, 0.12)",
              border: `1px solid ${coverage.missing_ranges.length === 0 ? "var(--good)" : "#faad14"}`,
              color: coverage.missing_ranges.length === 0 ? "var(--good)" : "#d48806",
            }}>
              {coverage.missing_ranges.length === 0 ? (
                <><CheckOutlined /> 全 {coverage.total} 章已覆盖（{coverage.covered}/{coverage.total}）</>
              ) : (
                <Tooltip title={
                  <div style={{ fontSize: 11 }}>
                    缺失范围：
                    {coverage.missing_ranges.slice(0, 10).map((r, i) => (
                      <div key={i}>章 {r[0]}{r[0] !== r[1] ? `–${r[1]}` : ""}</div>
                    ))}
                    {coverage.missing_ranges.length > 10 && <div>……</div>}
                  </div>
                }>
                  <span>
                    <WarningOutlined /> {coverage.covered}/{coverage.total} 章已覆盖，缺 {coverage.total - coverage.covered} 章
                  </span>
                </Tooltip>
              )}
            </div>
          )}
        </div>

        <table style={{ marginTop: 12 }}>
          <thead><tr><th>id</th><th>章节</th><th>状态</th><th>$</th><th>开始</th><th>结束</th><th>错误 / 操作</th></tr></thead>
          <tbody>
            {batches.map((b) => (
              <tr key={b.id}>
                <td>{b.id}</td>
                <td>{b.chapter_start}–{b.chapter_end - 1}</td>
                <td>
                  <span className={`tag ${
                    b.status === "done" ? "resolved" :
                    b.status === "failed" ? "dropped" :
                    b.status === "superseded" ? "" :
                    "open"
                  }`} style={b.status === "superseded" ? { background: "var(--panel-2)", color: "var(--muted)" } : undefined}>
                    {b.status}
                  </span>
                </td>
                <td>${b.cost_usd?.toFixed(4) ?? "0"}</td>
                <td className="muted">{b.created_at?.replace("T", " ").slice(0, 19)}</td>
                <td className="muted">{b.finished_at?.replace("T", " ").slice(0, 19)}</td>
                <td className="muted" style={{ maxWidth: 480 }}>
                  {b.status === "failed" && (
                    <button
                      onClick={() => retryBatch(b)}
                      style={{ padding: "2px 10px", fontSize: 11, marginRight: 8, background: "var(--accent)" }}
                    >
                      <RedoOutlined /> 重试
                    </button>
                  )}
                  {b.error && (
                    <span style={{ fontSize: 11, color: b.status === "failed" ? "var(--bad)" : "var(--muted)" }}>
                      {b.error.length > 120 ? b.error.slice(0, 120) + "…" : b.error}
                    </span>
                  )}
                </td>
              </tr>
            ))}
            {batches.length === 0 && <tr><td colSpan={7} className="muted">暂无批次</td></tr>}
          </tbody>
        </table>
      </div>

      {err && <div className="card" style={{ borderColor: "var(--bad)" }}>错误：{err}</div>}
    </>
  );
}
