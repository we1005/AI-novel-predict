"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Tag, Tooltip, Slider, Empty, Spin } from "antd";
import {
  UserOutlined,
  HeartOutlined,
  WarningOutlined,
  EyeInvisibleOutlined,
  EyeOutlined,
  TeamOutlined,
  ArrowLeftOutlined,
  SendOutlined,
} from "@ant-design/icons";
import { api } from "@/lib/api";
import PageTitle from "@/components/PageTitle";

type Profile = {
  id: number;
  entity_id: number;
  name?: string;
  role?: string;
  importance?: number;
  bio: string;
  desires: string[];
  fears: string[];
  moral_compass: string;
  voice_style: string;
  typical_actions: string[];
  relationships_summary: { name: string; label?: string; attitude?: string }[];
  secrets_known: { secret: string; learned_chapter?: number }[];
  secrets_hidden: string[];
  arc_so_far: string;
  last_built_chapter: number;
  cost_usd: number;
  updated_at: string;
};

type HistoryItem = {
  id: number;
  entity_id: number;
  after_chapter: number;
  question: string;
  answer: string;
  cost_usd: number;
  created_at: string;
};

export default function CharacterPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const entityId = Number(params.id);

  const [profile, setProfile] = useState<Profile | null>(null);
  const [profileErr, setProfileErr] = useState<string>("");
  const [chapterMax, setChapterMax] = useState<number>(1472);
  const [afterChapter, setAfterChapter] = useState<number>(1472);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [question, setQuestion] = useState<string>("");
  const [streaming, setStreaming] = useState<boolean>(false);
  const [streamText, setStreamText] = useState<string>("");
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    api.profileGet(entityId)
      .then((p) => {
        setProfile(p);
        if (p?.last_built_chapter) setAfterChapter(p.last_built_chapter);
      })
      .catch((e) => setProfileErr(String(e)));
    api.chapterCount().then((c) => setChapterMax(c.last || 1472)).catch(() => {});
    api.interviewHistory(entityId, 50).then(setHistory).catch(() => {});
  }, [entityId]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [history, streamText]);

  const ask = async () => {
    if (!question.trim() || streaming) return;
    const q = question.trim();
    setQuestion("");
    setStreaming(true);
    setStreamText("");
    let accum = "";
    try {
      await api.interviewStream(
        { character_id: entityId, after_chapter: afterChapter, question: q },
        (chunk) => {
          accum += chunk;
          setStreamText(accum);
        },
      );
      // refresh history (the backend persists after stream)
      const h = await api.interviewHistory(entityId, 50);
      setHistory(h);
      setStreamText("");
    } catch (e) {
      setStreamText(`[错误] ${String(e)}`);
    } finally {
      setStreaming(false);
    }
  };

  if (profileErr || (!profile && profileErr === "")) {
    if (profileErr) {
      return (
        <div className="container">
          <PageTitle title="角色档案" />
          <button className="ghost" onClick={() => router.back()}>
            <ArrowLeftOutlined /> 返回
          </button>
          <div className="card" style={{ marginTop: 16 }}>
            <Empty description={
              <div>
                <div style={{ marginBottom: 8 }}>没找到该角色的档案。</div>
                <div className="muted" style={{ fontSize: 12 }}>{profileErr}</div>
                <div style={{ marginTop: 12, fontSize: 12 }}>
                  请先到 <a onClick={() => router.push("/sim")} style={{ cursor: "pointer", color: "var(--accent)" }}>角色仿真</a> 页 → 点击"重建 top-N 档案"。
                </div>
              </div>
            } />
          </div>
        </div>
      );
    }
    return <div className="container"><Spin /> 加载中…</div>;
  }

  const p = profile!;

  return (
    <div className="container" style={{ maxWidth: 1100 }}>
      <button className="ghost" onClick={() => router.back()} style={{ marginBottom: 8 }}>
        <ArrowLeftOutlined /> 返回
      </button>

      <PageTitle
        title={p.name || `角色 #${entityId}`}
        subtitle={`${p.role || "person"} · 档案截至第 ${p.last_built_chapter} 章 · 重要度 ${p.importance ?? "?"}`}
      />

      {/* ---------- Profile card ---------- */}
      <div className="card" style={{ marginBottom: 18 }}>
        <h3 style={{ marginTop: 0 }}>
          <UserOutlined /> 简介
        </h3>
        <p style={{ fontFamily: "var(--serif)", lineHeight: 1.7, whiteSpace: "pre-wrap" }}>{p.bio}</p>

        {p.arc_so_far && (
          <>
            <h4>成长轨迹</h4>
            <p style={{ fontFamily: "var(--serif)", lineHeight: 1.7, whiteSpace: "pre-wrap", color: "var(--muted)" }}>
              {p.arc_so_far}
            </p>
          </>
        )}

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18, marginTop: 12 }}>
          <div>
            <h4><HeartOutlined style={{ color: "var(--accent)" }} /> 渴望</h4>
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {p.desires?.map((d, i) => <li key={i} style={{ marginBottom: 4 }}>{d}</li>)}
            </ul>
          </div>
          <div>
            <h4><WarningOutlined style={{ color: "var(--bad)" }} /> 恐惧</h4>
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              {p.fears?.map((d, i) => <li key={i} style={{ marginBottom: 4 }}>{d}</li>)}
            </ul>
          </div>
        </div>

        {p.moral_compass && (
          <>
            <h4 style={{ marginTop: 18 }}>道德坐标</h4>
            <p className="muted" style={{ fontStyle: "italic" }}>{p.moral_compass}</p>
          </>
        )}

        {p.voice_style && (
          <>
            <h4>说话风格 / 口头禅</h4>
            <p className="muted">{p.voice_style}</p>
          </>
        )}

        {p.typical_actions?.length > 0 && (
          <>
            <h4>典型行为</h4>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {p.typical_actions.map((t, i) => <Tag key={i}>{t}</Tag>)}
            </div>
          </>
        )}

        {p.relationships_summary?.length > 0 && (
          <>
            <h4 style={{ marginTop: 18 }}><TeamOutlined /> 关系</h4>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {p.relationships_summary.map((r, i) => (
                <Tooltip key={i} title={r.attitude || ""}>
                  <Tag color="blue">
                    {r.name}{r.label ? ` · ${r.label}` : ""}
                  </Tag>
                </Tooltip>
              ))}
            </div>
          </>
        )}

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18, marginTop: 18 }}>
          <div>
            <h4><EyeOutlined /> 已知秘密</h4>
            {p.secrets_known?.length > 0 ? (
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {p.secrets_known.map((s, i) => (
                  <li key={i} style={{ marginBottom: 6 }}>
                    {s.secret}
                    {s.learned_chapter ? <span className="muted" style={{ fontSize: 11 }}> · 第 {s.learned_chapter} 章得知</span> : null}
                  </li>
                ))}
              </ul>
            ) : <p className="muted" style={{ fontSize: 12 }}>—</p>}
          </div>
          <div>
            <h4><EyeInvisibleOutlined /> 自己藏的秘密</h4>
            {p.secrets_hidden?.length > 0 ? (
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {p.secrets_hidden.map((s, i) => <li key={i} style={{ marginBottom: 6 }}>{s}</li>)}
              </ul>
            ) : <p className="muted" style={{ fontSize: 12 }}>—</p>}
          </div>
        </div>
      </div>

      {/* ---------- Interview ---------- */}
      <div className="card">
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
          <h3 style={{ margin: 0 }}>对话</h3>
          <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 320 }}>
            <span className="muted" style={{ fontSize: 12 }}>截至第</span>
            <Slider
              min={1}
              max={chapterMax}
              value={afterChapter}
              onChange={setAfterChapter}
              style={{ width: 240 }}
              tooltip={{ formatter: (v) => `第 ${v} 章` }}
            />
            <span style={{ fontSize: 13, color: "var(--accent)", minWidth: 60 }}>
              第 {afterChapter} 章
            </span>
          </div>
        </div>

        <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
          决定 TA 应该知道哪些信息——拖低滑块可以问"早期的 TA"。
        </div>

        <div
          ref={scrollRef}
          style={{
            marginTop: 14,
            maxHeight: 480,
            overflowY: "auto",
            padding: 12,
            background: "var(--bg)",
            borderRadius: 8,
            border: "1px solid var(--border)",
          }}
        >
          {history.length === 0 && !streaming && !streamText && (
            <div className="muted" style={{ textAlign: "center", padding: 24, fontSize: 13 }}>
              还没有对话。试试问"你最近最担心的是什么？"或"你为什么不告诉 X 你的真实身份？"
            </div>
          )}

          {history.map((h) => (
            <div key={h.id} style={{ marginBottom: 18 }}>
              <Bubble who="me" text={h.question} note={`截至第 ${h.after_chapter} 章`} />
              <Bubble who="them" text={h.answer} name={p.name} />
            </div>
          ))}

          {streaming && (
            <div style={{ marginBottom: 18 }}>
              <Bubble who="me" text={"…"} note={`截至第 ${afterChapter} 章`} />
              <Bubble who="them" text={streamText || "…思考中"} name={p.name} streaming />
            </div>
          )}
        </div>

        <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) ask();
            }}
            placeholder="问 TA 一个问题…  (⌘/Ctrl + Enter 发送)"
            rows={2}
            style={{
              flex: 1,
              padding: 10,
              borderRadius: 6,
              border: "1px solid var(--border)",
              background: "var(--panel)",
              color: "inherit",
              fontFamily: "var(--serif)",
              resize: "vertical",
            }}
            disabled={streaming}
          />
          <button
            onClick={ask}
            disabled={streaming || !question.trim()}
            style={{ padding: "0 18px", minWidth: 80 }}
          >
            <SendOutlined /> {streaming ? "回答中…" : "发送"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Bubble({
  who, text, name, note, streaming,
}: {
  who: "me" | "them";
  text: string;
  name?: string;
  note?: string;
  streaming?: boolean;
}) {
  const me = who === "me";
  return (
    <div style={{ display: "flex", justifyContent: me ? "flex-end" : "flex-start", marginBottom: 6 }}>
      <div style={{ maxWidth: "78%" }}>
        {(name || note) && (
          <div className="muted" style={{
            fontSize: 11,
            marginBottom: 4,
            textAlign: me ? "right" : "left",
          }}>
            {me ? note : (name || "TA")}
          </div>
        )}
        <div style={{
          padding: "10px 14px",
          borderRadius: 12,
          background: me ? "rgba(122,162,247,0.15)" : "var(--panel)",
          border: me ? "1px solid rgba(122,162,247,0.35)" : "1px solid var(--border)",
          fontFamily: "var(--serif)",
          lineHeight: 1.7,
          whiteSpace: "pre-wrap",
          fontSize: 14,
        }}>
          {text}
          {streaming && <span className="cursor-blink" style={{ marginLeft: 2 }}>▍</span>}
        </div>
      </div>
    </div>
  );
}
