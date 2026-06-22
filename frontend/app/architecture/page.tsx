"use client";

import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Spin, Tag, Tooltip } from "antd";
import {
  BookOutlined,
  DatabaseOutlined,
  ExperimentOutlined,
  BulbOutlined,
  EditOutlined,
  TeamOutlined,
  RobotOutlined,
  DeploymentUnitOutlined,
} from "@ant-design/icons";
import PageTitle from "@/components/PageTitle";

type DocFile = { file: string; content: string };

const DOC_META: Record<string, { label: string; icon: React.ReactNode; tag: string; tagColor: string }> = {
  "00-总览.md":             { label: "总览",         icon: <BookOutlined />,        tag: "Overview",  tagColor: "blue" },
  "01-上下文记忆模块.md":     { label: "记忆模块",     icon: <DatabaseOutlined />,    tag: "Memory",    tagColor: "purple" },
  "02-语料抽取链路.md":       { label: "语料抽取",     icon: <ExperimentOutlined />,  tag: "Ingest",    tagColor: "geekblue" },
  "03-预测链路.md":          { label: "预测链路",     icon: <BulbOutlined />,        tag: "Predict",   tagColor: "gold" },
  "04-写作链路.md":          { label: "写作链路",     icon: <EditOutlined />,        tag: "Draft",     tagColor: "green" },
  "05-角色仿真链路.md":       { label: "角色仿真",     icon: <TeamOutlined />,        tag: "Sim",       tagColor: "magenta" },
  "06-Agent与Prompt设计.md": { label: "Agent & Prompt", icon: <RobotOutlined />,    tag: "Agents",    tagColor: "volcano" },
  "07-整本故事弧推演链路.md": { label: "整本故事弧推演", icon: <DeploymentUnitOutlined />, tag: "Whole-Book", tagColor: "cyan" },
};

export default function ArchitecturePage() {
  const [files, setFiles] = useState<string[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [doc, setDoc] = useState<DocFile | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Load file list once
  useEffect(() => {
    fetch("/api/docs")
      .then((r) => r.json())
      .then((d) => {
        const fs: string[] = d.files || [];
        setFiles(fs);
        if (fs.length > 0) setActive(fs[0]);
      })
      .catch((e) => setErr(String(e)));
  }, []);

  // Load active doc
  useEffect(() => {
    if (!active) return;
    setLoading(true);
    setErr(null);
    fetch(`/api/docs?file=${encodeURIComponent(active)}`)
      .then((r) => r.json())
      .then((d) => {
        if (d.error) throw new Error(d.error);
        setDoc(d);
      })
      .catch((e) => setErr(String(e)))
      .finally(() => setLoading(false));
  }, [active]);

  const meta = (f: string) => DOC_META[f] || { label: f.replace(".md", ""), icon: <BookOutlined />, tag: "", tagColor: "default" };

  return (
    <div style={{ display: "grid", gridTemplateColumns: "260px 1fr", gap: 24, alignItems: "flex-start" }}>
      {/* ---------- Sidebar ---------- */}
      <aside
        style={{
          position: "sticky",
          top: 16,
          maxHeight: "calc(100vh - 32px)",
          overflowY: "auto",
          background: "var(--panel)",
          border: "1px solid var(--border)",
          borderRadius: 10,
          padding: "14px 10px",
        }}
      >
        <div style={{
          padding: "0 6px 12px",
          borderBottom: "1px solid var(--border)",
          marginBottom: 10,
          fontFamily: "var(--decorative)",
          fontSize: 22,
          color: "var(--accent-2)",
          letterSpacing: 3,
        }}>
          架构文档
        </div>

        {files.length === 0 && !err && <Spin size="small" />}
        {err && <div className="muted" style={{ padding: 10, fontSize: 12 }}>加载失败：{err}</div>}

        <nav style={{ display: "flex", flexDirection: "column", gap: 2 }}>
          {files.map((f) => {
            const m = meta(f);
            const isActive = f === active;
            return (
              <button
                key={f}
                onClick={() => setActive(f)}
                className={isActive ? "" : "ghost"}
                style={{
                  textAlign: "left",
                  padding: "10px 12px",
                  fontSize: 13,
                  border: "none",
                  background: isActive ? "rgba(122,162,247,0.15)" : "transparent",
                  borderLeft: isActive ? "3px solid var(--accent)" : "3px solid transparent",
                  borderRadius: 0,
                  color: isActive ? "var(--accent-2)" : "var(--text)",
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  cursor: "pointer",
                }}
              >
                <span style={{ fontSize: 14, opacity: 0.85 }}>{m.icon}</span>
                <span style={{ flex: 1 }}>{m.label}</span>
              </button>
            );
          })}
        </nav>
      </aside>

      {/* ---------- Main content ---------- */}
      <article style={{ minWidth: 0 }}>
        <PageTitle
          title="墨笔架构"
          subtitle="多 agent 协作 · 章节有时序的外部记忆 · 发散→收敛→执行"
        />

        {active && (
          <div style={{ marginBottom: 14, display: "flex", alignItems: "center", gap: 10 }}>
            <Tag color={meta(active).tagColor}>
              {meta(active).icon} {meta(active).tag}
            </Tag>
            <Tooltip title="原始文件路径">
              <span className="muted" style={{ fontSize: 11, fontFamily: "monospace" }}>
                墨笔-agent架构设计docs/{active}
              </span>
            </Tooltip>
          </div>
        )}

        <div className="card" style={{ padding: "24px 32px" }}>
          {loading && <Spin />}
          {!loading && doc && (
            <div className="markdown-body">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {doc.content}
              </ReactMarkdown>
            </div>
          )}
        </div>
      </article>

      <style jsx global>{`
        .markdown-body {
          font-family: var(--serif);
          line-height: 1.75;
          color: var(--text);
          font-size: 15px;
        }
        .markdown-body h1 {
          font-family: var(--decorative);
          font-size: 30px;
          color: var(--accent-2);
          margin: 0 0 18px;
          padding-bottom: 12px;
          border-bottom: 2px solid var(--border);
          letter-spacing: 3px;
          font-weight: 400;
        }
        .markdown-body h2 {
          margin: 28px 0 12px;
          font-size: 22px;
          color: var(--accent);
          padding-left: 10px;
          border-left: 4px solid var(--accent);
        }
        .markdown-body h3 {
          margin: 22px 0 10px;
          font-size: 17px;
          color: var(--accent-2);
        }
        .markdown-body h4 {
          margin: 18px 0 6px;
          font-size: 15px;
          color: var(--text);
        }
        .markdown-body p { margin: 10px 0; }
        .markdown-body blockquote {
          border-left: 3px solid var(--accent);
          margin: 14px 0;
          padding: 6px 14px;
          background: rgba(122,162,247,0.08);
          color: var(--muted);
          font-style: italic;
          border-radius: 0 6px 6px 0;
        }
        .markdown-body ul, .markdown-body ol {
          padding-left: 24px;
          margin: 10px 0;
        }
        .markdown-body li { margin: 4px 0; }
        .markdown-body a {
          color: var(--accent);
          text-decoration: none;
          border-bottom: 1px dashed var(--accent);
        }
        .markdown-body a:hover { opacity: 0.8; }
        .markdown-body code {
          background: var(--bg);
          padding: 2px 6px;
          border-radius: 4px;
          font-size: 12.5px;
          font-family: ui-monospace, SFMono-Regular, monospace;
          color: var(--accent-2);
          border: 1px solid var(--border);
        }
        .markdown-body pre {
          background: var(--bg);
          border: 1px solid var(--border);
          border-radius: 8px;
          padding: 14px 16px;
          overflow-x: auto;
          font-size: 12.5px;
          line-height: 1.55;
          margin: 14px 0;
        }
        .markdown-body pre code {
          background: transparent;
          padding: 0;
          border: none;
          color: var(--text);
          font-size: inherit;
        }
        .markdown-body table {
          border-collapse: collapse;
          margin: 14px 0;
          font-size: 13px;
          width: 100%;
        }
        .markdown-body th, .markdown-body td {
          border: 1px solid var(--border);
          padding: 8px 12px;
          text-align: left;
          vertical-align: top;
        }
        .markdown-body th {
          background: var(--bg);
          font-weight: 600;
          color: var(--accent-2);
        }
        .markdown-body hr {
          border: none;
          border-top: 1px dashed var(--border);
          margin: 24px 0;
        }
        .markdown-body strong { color: var(--accent-2); font-weight: 600; }
      `}</style>
    </div>
  );
}
