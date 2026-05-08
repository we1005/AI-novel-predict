"use client";

import { memo, useEffect, useMemo, useState } from "react";
import {
  ReactFlow,
  Controls,
  MiniMap,
  Background,
  BackgroundVariant,
  MarkerType,
  Position,
  Handle,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import dagre from "dagre";
import { Drawer, Tag, Typography } from "antd";
import { BookOutlined, BranchesOutlined } from "@ant-design/icons";
import Link from "next/link";
import { api } from "@/lib/api";

const { Title, Paragraph, Text } = Typography;

const NODE_W = 280;
const NODE_H = 170;
const SUB_W = 200;
const SUB_H = 100;

type ChapterRaw = any;

type FsLite = { id: number; type: string; status: string; description: string; planted_chapter: number; resolved_chapter: number | null };

function layout(chapters: ChapterRaw[], fsByChapterAddressed: Record<number, FsLite[]>): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "TB", ranksep: 90, nodesep: 60, edgesep: 28 });

  // main chapter nodes
  for (const c of chapters) {
    g.setNode(`ch-${c.chapter_index}`, { width: NODE_W, height: NODE_H });
  }
  // chapter-to-chapter
  for (let i = 0; i < chapters.length - 1; i++) {
    g.setEdge(`ch-${chapters[i].chapter_index}`, `ch-${chapters[i + 1].chapter_index}`);
  }
  // subplot nodes (one per addressed-foreshadow per chapter, capped)
  const subEdges: Array<{ from: string; to: string }> = [];
  for (const c of chapters) {
    const fs = fsByChapterAddressed[c.chapter_index] || [];
    fs.slice(0, 2).forEach((f, j) => {
      const subId = `sub-${c.chapter_index}-${f.id}`;
      g.setNode(subId, { width: SUB_W, height: SUB_H });
      g.setEdge(`ch-${c.chapter_index}`, subId);
      subEdges.push({ from: `ch-${c.chapter_index}`, to: subId });
    });
  }

  dagre.layout(g);

  const nodes: Node[] = [];
  for (const c of chapters) {
    const id = `ch-${c.chapter_index}`;
    const pos = g.node(id);
    nodes.push({
      id,
      type: "chapter",
      data: c,
      position: { x: (pos?.x ?? 0) - NODE_W / 2, y: (pos?.y ?? 0) - NODE_H / 2 },
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
      width: NODE_W,
      height: NODE_H,
    });
    const fs = fsByChapterAddressed[c.chapter_index] || [];
    fs.slice(0, 2).forEach((f) => {
      const subId = `sub-${c.chapter_index}-${f.id}`;
      const pos = g.node(subId);
      nodes.push({
        id: subId,
        type: "subplot",
        data: f,
        position: { x: (pos?.x ?? 0) - SUB_W / 2, y: (pos?.y ?? 0) - SUB_H / 2 },
        targetPosition: Position.Left,
        width: SUB_W,
        height: SUB_H,
      });
    });
  }

  const edges: Edge[] = [];
  // Main chain — green animated
  for (let i = 0; i < chapters.length - 1; i++) {
    edges.push({
      id: `main-${i}`,
      source: `ch-${chapters[i].chapter_index}`,
      target: `ch-${chapters[i + 1].chapter_index}`,
      type: "smoothstep",
      animated: true,
      style: { stroke: "var(--c-character)", strokeWidth: 2 },
      markerEnd: { type: MarkerType.ArrowClosed, color: "var(--c-character)" },
    });
  }
  // Subplot edges — purple dashed with label
  subEdges.forEach((e, i) => {
    edges.push({
      id: `sub-${i}`,
      source: e.from,
      target: e.to,
      type: "smoothstep",
      animated: false,
      label: "支线",
      labelStyle: { fill: "var(--c-subplot)", fontSize: 11, fontWeight: 500 },
      labelBgStyle: { fill: "var(--panel)", fillOpacity: 0.85 },
      labelBgPadding: [3, 4] as [number, number],
      style: { stroke: "var(--c-subplot)", strokeDasharray: "5,5", strokeWidth: 1.4 },
    });
  });

  return { nodes, edges };
}

// ---------------------------------------------------------------------------
// Chapter node — laid out like the legacy 剧情大纲可视化 cards
// ---------------------------------------------------------------------------

const ChapterNode = memo(({ data }: NodeProps<Node<any>>) => {
  const characters: string[] = data.involved_entities || [];
  const turningPoints = (data.key_events || []).length;
  const fsCount = (data.foreshadow_ids_addressed || []).length;

  return (
    <div style={{
      width: NODE_W,
      borderRadius: 8,
      background: "var(--panel)",
      border: "1px solid var(--border)",
      overflow: "hidden",
      boxShadow: "0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -1px rgba(0,0,0,0.04)",
      cursor: "pointer",
    }}>
      <Handle type="target" position={Position.Top}
        style={{ background: "var(--c-character)", width: 8, height: 8, top: -4 }} />
      {/* header strip */}
      <div style={{
        background: "var(--panel-2)",
        borderBottom: "1px solid var(--border)",
        padding: "6px 12px",
        display: "flex", alignItems: "center", gap: 6,
        fontSize: 12, color: "var(--muted)", fontWeight: 600,
      }}>
        <BookOutlined style={{ color: "var(--c-character)" }} />
        <span>第 {data.chapter_index} 章</span>
        <span style={{ marginLeft: "auto", fontWeight: 400, fontSize: 11 }}>
          ~{data.word_target || 3000} 字
        </span>
      </div>
      {/* body */}
      <div style={{ padding: "10px 14px 12px" }}>
        <div className="prose-cn" style={{
          fontSize: 16, fontWeight: 600, color: "var(--text)",
          marginBottom: 6, lineHeight: 1.35,
          whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
        }}>
          {data.title}
        </div>
        {characters.length > 0 && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 8 }}>
            {characters.slice(0, 4).map((c) => (
              <Tag key={c} color="blue" style={{ margin: 0, fontSize: 11 }}>{c}</Tag>
            ))}
            {characters.length > 4 && (
              <Tag style={{ margin: 0, fontSize: 11 }}>+{characters.length - 4}</Tag>
            )}
          </div>
        )}
        <div style={{ fontSize: 12, color: "var(--muted)" }}>
          Turning Points: <span style={{ fontWeight: 600, color: "var(--text)" }}>{turningPoints}</span>
          {fsCount > 0 && (
            <>
              {" · "}收束伏笔: <span style={{ fontWeight: 600, color: "var(--c-foreshadow)" }}>{fsCount}</span>
            </>
          )}
        </div>
      </div>
      <Handle type="source" position={Position.Bottom}
        style={{ background: "var(--c-character)", width: 8, height: 8, bottom: -4 }} />
    </div>
  );
});
ChapterNode.displayName = "ChapterNode";

// ---------------------------------------------------------------------------
// Subplot node — small dashed-purple card with foreshadow description
// ---------------------------------------------------------------------------

const SubPlotNode = memo(({ data }: NodeProps<Node<FsLite>>) => {
  const desc = data.description || "";
  return (
    <div style={{
      width: SUB_W,
      borderRadius: 6,
      background: "rgba(178, 127, 235, 0.08)",
      border: "1px dashed var(--c-subplot)",
      padding: "8px 10px",
      cursor: "pointer",
    }}>
      <Handle type="target" position={Position.Left}
        style={{ background: "var(--c-subplot)", width: 6, height: 6, left: -3 }} />
      <div style={{ display: "flex", alignItems: "center", gap: 4, marginBottom: 4 }}>
        <BranchesOutlined style={{ color: "var(--c-subplot)", fontSize: 11 }} />
        <span style={{ fontSize: 11, color: "var(--c-subplot)", fontWeight: 600 }}>
          伏笔 #{data.id}
        </span>
        <Tag style={{
          margin: 0, fontSize: 10, padding: "0 4px",
          color: data.status === "open" ? "var(--c-foreshadow)" : "var(--good)",
          background: data.status === "open" ? "rgba(250,173,20,.15)" : "rgba(82,196,26,.15)",
          border: 0,
        }}>
          {data.status === "open" ? "未收" : "收束"}
        </Tag>
      </div>
      <div style={{
        fontSize: 11, color: "var(--text)", lineHeight: 1.5,
        display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: "vertical",
        overflow: "hidden",
      }}>
        {desc}
      </div>
    </div>
  );
});
SubPlotNode.displayName = "SubPlotNode";

// ---------------------------------------------------------------------------

export default function ChapterFlowGraph({ runId, chapters, height }: { runId: number; chapters: any[]; height?: number | string }) {
  const [allFs, setAllFs] = useState<FsLite[]>([]);

  useEffect(() => {
    // Pull both open and resolved foreshadowings so the side-nodes can show
    // anything a chapter outline references.
    api.foreshadowings("all").then((rows: any[]) => {
      setAllFs(rows.map((r) => ({
        id: r.id, type: r.type, status: r.status,
        description: r.description, planted_chapter: r.planted_chapter,
        resolved_chapter: r.resolved_chapter,
      })));
    }).catch(() => setAllFs([]));
  }, []);

  const fsById = useMemo(() => {
    const m: Record<number, FsLite> = {};
    for (const f of allFs) m[f.id] = f;
    return m;
  }, [allFs]);

  // For each chapter, collect addressed foreshadows (with desc lookup)
  const fsByChapter = useMemo(() => {
    const m: Record<number, FsLite[]> = {};
    for (const c of chapters || []) {
      const ids = c.foreshadow_ids_addressed || [];
      m[c.chapter_index] = ids.map((id: number) => fsById[id]).filter(Boolean);
    }
    return m;
  }, [chapters, fsById]);

  const { nodes, edges } = useMemo(
    () => layout(chapters || [], fsByChapter),
    [chapters, fsByChapter],
  );

  const [selected, setSelected] = useState<any | null>(null);
  const [selectedKind, setSelectedKind] = useState<"chapter" | "subplot" | null>(null);

  const nodeTypes = useMemo(() => ({ chapter: ChapterNode, subplot: SubPlotNode }), []);

  return (
    <div style={{
      width: "100%", height: height ?? 700,
      background: "var(--panel-2)",
      borderRadius: 8, border: "1px solid var(--border)",
      overflow: "hidden", position: "relative",
    }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        minZoom={0.2}
        maxZoom={1.5}
        onNodeClick={(_, n) => {
          setSelected(n.data);
          setSelectedKind(n.type === "subplot" ? "subplot" : "chapter");
        }}
      >
        <Controls showInteractive={false} />
        <MiniMap pannable zoomable maskColor="rgba(14,16,21,0.6)"
                 nodeColor={(n) => n.type === "subplot" ? "var(--c-subplot)" : "var(--c-character)"} />
        <Background variant={BackgroundVariant.Dots} gap={16} size={1} color="var(--border)" />
      </ReactFlow>

      <Drawer
        title={
          selectedKind === "chapter" && selected
            ? `第 ${selected.chapter_index} 章 · ${selected.title}`
            : selectedKind === "subplot" && selected
              ? `伏笔 #${selected.id}`
              : ""
        }
        placement="right"
        width={520}
        open={!!selected}
        onClose={() => setSelected(null)}
        mask={false}
      >
        {selected && selectedKind === "chapter" && (
          <ChapterDrawer chapter={selected} runId={runId} />
        )}
        {selected && selectedKind === "subplot" && (
          <SubplotDrawer fs={selected} />
        )}
      </Drawer>
    </div>
  );
}

function ChapterDrawer({ chapter, runId }: { chapter: any; runId: number }) {
  return (
    <div className="prose-cn">
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 12 }}>
        {chapter.pacing && <Tag color="blue">节奏: {chapter.pacing}</Tag>}
        <Tag>~{chapter.word_target} 字</Tag>
        {(chapter.foreshadow_ids_addressed || []).length > 0 && (
          <Tag color="gold">收束伏笔 #{chapter.foreshadow_ids_addressed.join(", #")}</Tag>
        )}
      </div>

      {chapter.intent && (
        <>
          <Title level={5} style={{ marginTop: 0, color: "var(--text)", borderLeft: "3px solid var(--c-story)", paddingLeft: 8 }}>
            意图
          </Title>
          <Paragraph style={{ color: "var(--text)" }}>{chapter.intent}</Paragraph>
        </>
      )}

      {(chapter.must_include || []).length > 0 && (
        <>
          <Title level={5} style={{ color: "var(--text)", borderLeft: "3px solid var(--c-world)", paddingLeft: 8 }}>
            必含元素
          </Title>
          <ul style={{ paddingLeft: 18, color: "var(--text)" }}>
            {chapter.must_include.map((x: string, i: number) => <li key={i}>{x}</li>)}
          </ul>
        </>
      )}

      {(chapter.must_avoid || []).length > 0 && (
        <>
          <Title level={5} style={{ color: "var(--text)", borderLeft: "3px solid var(--bad)", paddingLeft: 8 }}>
            必避内容
          </Title>
          <ul style={{ paddingLeft: 18, color: "var(--text)" }}>
            {chapter.must_avoid.map((x: string, i: number) => <li key={i}>{x}</li>)}
          </ul>
        </>
      )}

      {(chapter.key_events || []).length > 0 && (
        <>
          <Title level={5} style={{ color: "var(--text)", borderLeft: "3px solid var(--c-foreshadow)", paddingLeft: 8 }}>
            关键事件
          </Title>
          <ol style={{ paddingLeft: 18, color: "var(--text)" }}>
            {chapter.key_events.map((x: string, i: number) => <li key={i}>{x}</li>)}
          </ol>
        </>
      )}

      {(chapter.involved_entities || []).length > 0 && (
        <>
          <Title level={5} style={{ color: "var(--text)", borderLeft: "3px solid var(--c-character)", paddingLeft: 8 }}>
            涉及人物
          </Title>
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
            {chapter.involved_entities.map((n: string) => <Tag key={n} color="blue">{n}</Tag>)}
          </div>
        </>
      )}

      {chapter.ending_hook && (
        <>
          <Title level={5} style={{ color: "var(--text)", borderLeft: "3px solid var(--c-subplot)", paddingLeft: 8, marginTop: 16 }}>
            章末钩子
          </Title>
          <Paragraph style={{ color: "var(--text)", fontStyle: "italic" }}>{chapter.ending_hook}</Paragraph>
        </>
      )}

      <div style={{ marginTop: 24, display: "flex", justifyContent: "flex-end" }}>
        <Link
          href={`/draft?outline_run_id=${runId}&chapter_index=${chapter.chapter_index}`}
          className="btn"
          style={{
            padding: "6px 14px", fontSize: 13, textDecoration: "none",
            background: "var(--accent-2)", color: "#fff",
            borderRadius: 6, fontWeight: 600,
          }}
        >
          去写 →
        </Link>
      </div>
    </div>
  );
}

function SubplotDrawer({ fs }: { fs: FsLite }) {
  return (
    <div className="prose-cn">
      <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
        <Tag color="purple">{fs.type}</Tag>
        <Tag color={fs.status === "open" ? "gold" : "green"}>
          {fs.status === "open" ? "未收束" : "已收束"}
        </Tag>
        <Tag>埋于第 {fs.planted_chapter} 章</Tag>
        {fs.resolved_chapter && <Tag>收于第 {fs.resolved_chapter} 章</Tag>}
      </div>
      <Paragraph style={{ color: "var(--text)", whiteSpace: "pre-wrap" }}>
        {fs.description}
      </Paragraph>
    </div>
  );
}
