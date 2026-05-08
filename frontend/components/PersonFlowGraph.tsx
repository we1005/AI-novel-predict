"use client";

import { memo, useMemo, useState } from "react";
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

const { Title, Paragraph } = Typography;

type RawNode = {
  data: {
    id: string; label: string; importance: number;
    first_chapter?: number; full_name?: string; description?: string;
    role?: "protagonist" | "antagonist" | "ally" | "supporting" | "minor";
    rel_count?: number;
  };
};
type RawEdge = {
  data: {
    id: string; source: string; target: string;
    weight: number; label?: string; description?: string;
    kind?: "labeled" | "co_occur"; status?: "active" | "ended";
  };
};

const ROLE_COLOR: Record<string, string> = {
  protagonist: "#ef4444",   // 红
  antagonist: "#a855f7",    // 紫
  ally: "#3b82f6",          // 蓝
  supporting: "#f59e0b",    // 橙
  minor: "#9ca3af",         // 灰
};
const ROLE_LABEL: Record<string, string> = {
  protagonist: "主角",
  antagonist: "反派",
  ally: "盟友",
  supporting: "配角",
  minor: "龙套",
};

function nodeRadiusByRole(role: string | undefined, importance: number): number {
  if (role === "protagonist") return 78;
  if (role === "antagonist") return 64;
  if (role === "ally") return 56;
  if (role === "supporting") return 48;
  // for minors / unknown, fall back to importance scaling
  return Math.max(36, Math.min(50, 36 + Math.log2(Math.max(1, importance)) * 4));
}

function layout(rawNodes: RawNode[], rawEdges: RawEdge[]): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "LR", ranksep: 140, nodesep: 60, edgesep: 30 });

  for (const n of rawNodes) {
    const r = nodeRadiusByRole(n.data.role, n.data.importance);
    g.setNode(n.data.id, { width: r + 40, height: r + 12 });
  }
  for (const e of rawEdges) g.setEdge(e.data.source, e.data.target);
  dagre.layout(g);

  const nodes: Node[] = rawNodes.map((n) => {
    const pos = g.node(n.data.id);
    const r = nodeRadiusByRole(n.data.role, n.data.importance);
    return {
      id: n.data.id,
      type: "person",
      data: { ...n.data, radius: r },
      position: { x: (pos?.x ?? 0) - r / 2, y: (pos?.y ?? 0) - r / 2 },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      width: r,
      height: r,
    };
  });

  const maxW = Math.max(1, ...rawEdges.map((e) => e.data.weight));
  const edges: Edge[] = rawEdges.map((e) => {
    const labeled = e.data.kind === "labeled";
    const ended = e.data.status === "ended";
    return {
      id: e.data.id,
      source: e.data.source,
      target: e.data.target,
      label: labeled ? e.data.label : undefined,
      type: labeled ? "default" : "default",
      animated: false,
      labelStyle: {
        fill: "var(--text)",
        fontSize: 11,
        fontWeight: 500,
      },
      labelBgStyle: {
        fill: "var(--panel)",
        fillOpacity: 0.92,
      },
      labelBgPadding: [4, 6] as [number, number],
      labelBgBorderRadius: 4,
      style: {
        stroke: labeled ? "var(--c-story)" : "var(--border)",
        strokeWidth: labeled ? 1 + (e.data.weight / 10) * 2 : 1,
        strokeDasharray: ended ? "5,4" : (labeled ? undefined : "3,3"),
        opacity: labeled ? 0.9 : 0.4,
      },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: labeled ? "var(--c-story)" : "var(--border)",
      },
    };
  });

  return { nodes, edges };
}

const PersonNode = memo(({ data }: NodeProps<Node<any>>) => {
  const r = data.radius || 50;
  const role = data.role || "minor";
  const color = ROLE_COLOR[role] || ROLE_COLOR.minor;
  const isProtagonist = role === "protagonist";
  return (
    <div style={{
      width: r, height: r,
      borderRadius: "50%",
      background: color,
      border: isProtagonist ? "3px solid var(--accent-2)" : `2px solid ${color}`,
      display: "flex", flexDirection: "column",
      alignItems: "center", justifyContent: "center",
      cursor: "pointer",
      boxShadow: isProtagonist
        ? `0 0 16px ${color}80, 0 2px 6px rgba(0,0,0,0.3)`
        : `0 2px 6px rgba(0,0,0,0.25)`,
      color: "#fff",
      textShadow: "0 1px 2px rgba(0,0,0,0.4)",
      padding: 2,
    }}>
      <Handle type="target" position={Position.Left} style={{ background: "transparent", border: 0 }} />
      <div className="prose-cn" style={{
        fontWeight: 700,
        fontSize: r > 64 ? 14 : r > 50 ? 12 : 10,
        textAlign: "center", lineHeight: 1.1,
        maxWidth: r - 8, overflow: "hidden",
      }}>
        {data.label}
      </div>
      <div style={{
        fontSize: r > 64 ? 10 : 9, opacity: 0.85, marginTop: 2,
        fontFamily: "var(--sans)",
      }}>
        {ROLE_LABEL[role] || role}
      </div>
      {(data.rel_count || 0) > 0 && (
        <div style={{
          fontSize: r > 64 ? 10 : 9, opacity: 0.8,
          fontFamily: "var(--sans)",
        }}>
          {data.rel_count} 条关系
        </div>
      )}
      <Handle type="source" position={Position.Right} style={{ background: "transparent", border: 0 }} />
    </div>
  );
});
PersonNode.displayName = "PersonNode";

export default function PersonFlowGraph({ nodes: rawNodes, edges: rawEdges, height = 720 }: {
  nodes: RawNode[]; edges: RawEdge[]; height?: number;
}) {
  const { nodes, edges } = useMemo(() => layout(rawNodes || [], rawEdges || []), [rawNodes, rawEdges]);
  const [selectedNode, setSelectedNode] = useState<any | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<any | null>(null);

  const nodeTypes = useMemo(() => ({ person: PersonNode }), []);

  return (
    <div style={{
      width: "100%", height,
      background: "var(--panel-2)", borderRadius: 8, border: "1px solid var(--border)",
      overflow: "hidden", position: "relative",
    }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        minZoom={0.2}
        maxZoom={1.6}
        onNodeClick={(_, n) => { setSelectedNode(n.data); setSelectedEdge(null); }}
        onEdgeClick={(_, e) => { setSelectedEdge(e.data); setSelectedNode(null); }}
      >
        <Controls showInteractive={false} />
        <MiniMap pannable zoomable maskColor="rgba(14,16,21,0.6)"
                 style={{ background: "var(--panel-2)" }}
                 nodeColor={(n) => ROLE_COLOR[(n.data as any)?.role || "minor"] || "#9ca3af"} />
        <Background variant={BackgroundVariant.Dots} gap={16} size={1} color="var(--border)" />
      </ReactFlow>

      {/* Legend in bottom-left */}
      <div style={{
        position: "absolute", left: 16, bottom: 16,
        background: "var(--panel)", border: "1px solid var(--border)",
        borderRadius: 6, padding: "8px 12px",
        boxShadow: "0 2px 8px rgba(0,0,0,0.2)",
        zIndex: 5,
      }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: "var(--muted)", marginBottom: 6, letterSpacing: 1 }}>
          角色类型图例
        </div>
        {(["protagonist", "antagonist", "ally", "supporting", "minor"] as const).map((r) => (
          <div key={r} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3, fontSize: 12 }}>
            <span style={{
              width: 10, height: 10, borderRadius: "50%",
              background: ROLE_COLOR[r],
              border: r === "protagonist" ? "1.5px solid var(--accent-2)" : "none",
            }} />
            <span style={{ color: "var(--text)" }}>{ROLE_LABEL[r]}</span>
          </div>
        ))}
        <div style={{ borderTop: "1px solid var(--border)", marginTop: 6, paddingTop: 6, fontSize: 11, color: "var(--muted)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
            <span style={{ width: 18, height: 1.5, background: "var(--c-story)" }} /> 标注关系
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ width: 18, height: 1, background: "var(--border)", borderTop: "1px dashed var(--border)" }} /> 共同出现
          </div>
        </div>
      </div>

      {/* Node Drawer */}
      <Drawer
        title={selectedNode?.full_name || selectedNode?.label || ""}
        placement="right"
        width={420}
        open={!!selectedNode}
        onClose={() => setSelectedNode(null)}
        mask={false}
      >
        {selectedNode && (
          <div className="prose-cn">
            <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginBottom: 12 }}>
              <Tag color={ROLE_COLOR[selectedNode.role || "minor"]?.startsWith("#") ? undefined : "default"}
                style={{ background: ROLE_COLOR[selectedNode.role || "minor"], color: "#fff", border: 0 }}>
                {ROLE_LABEL[selectedNode.role || "minor"]}
              </Tag>
              <Tag color="purple">importance {selectedNode.importance}</Tag>
              {selectedNode.first_chapter && <Tag>首登场 第 {selectedNode.first_chapter} 章</Tag>}
              {selectedNode.rel_count > 0 && <Tag color="blue">{selectedNode.rel_count} 条关系</Tag>}
            </div>
            {selectedNode.description ? (
              <Paragraph style={{ color: "var(--text)", whiteSpace: "pre-wrap" }}>
                {selectedNode.description}
              </Paragraph>
            ) : (
              <Paragraph type="secondary">暂无描述</Paragraph>
            )}
            <a
              href={`/character/${selectedNode.id}`}
              style={{
                display: "inline-block",
                marginTop: 8,
                padding: "6px 12px",
                background: "var(--accent)",
                color: "#fff",
                borderRadius: 6,
                fontSize: 13,
                textDecoration: "none",
              }}
            >
              找 TA 对话 →
            </a>
          </div>
        )}
      </Drawer>

      {/* Edge Drawer */}
      <Drawer
        title={selectedEdge?.label || "关系"}
        placement="right"
        width={420}
        open={!!selectedEdge}
        onClose={() => setSelectedEdge(null)}
        mask={false}
      >
        {selectedEdge && (
          <div className="prose-cn">
            <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginBottom: 12 }}>
              {selectedEdge.weight && <Tag color="blue">叙事权重 {selectedEdge.weight}</Tag>}
              {selectedEdge.status && (
                <Tag color={selectedEdge.status === "active" ? "green" : "red"}>
                  {selectedEdge.status === "active" ? "进行中" : "已结束"}
                </Tag>
              )}
            </div>
            {selectedEdge.description ? (
              <Paragraph style={{ color: "var(--text)", whiteSpace: "pre-wrap" }}>
                {selectedEdge.description}
              </Paragraph>
            ) : (
              <Paragraph type="secondary">无更多描述（这是按共同出现推断的弱关系）</Paragraph>
            )}
          </div>
        )}
      </Drawer>
    </div>
  );
}
