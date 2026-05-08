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
  type Node,
  type Edge,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import dagre from "dagre";
import { Drawer, Tag, Typography } from "antd";

const { Title, Paragraph, Text } = Typography;

const KIND_COLOR: Record<string, string> = {
  origin: "#bb9af7",
  truth: "#7aa2f7",
  agent: "#f7768e",
  event: "#faad14",
  consequence: "#9ece6a",
};
const KIND_LABEL: Record<string, string> = {
  origin: "本源",
  truth: "真相",
  agent: "动机",
  event: "事件",
  consequence: "后果",
};

const NODE_SIZE: Record<string, { w: number; h: number }> = {
  origin: { w: 220, h: 80 },
  truth: { w: 200, h: 70 },
  agent: { w: 180, h: 64 },
  event: { w: 180, h: 60 },
  consequence: { w: 200, h: 70 },
};

type RawNode = { id: string; label: string; kind: string; description?: string };
type RawEdge = { from: string; to: string; relation?: string };

function layout(rawNodes: RawNode[], rawEdges: RawEdge[]): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "TB", ranksep: 80, nodesep: 50, edgesep: 24 });

  for (const n of rawNodes) {
    const sz = NODE_SIZE[n.kind] || { w: 200, h: 70 };
    g.setNode(n.id, sz);
  }
  for (const e of rawEdges) g.setEdge(e.from, e.to);

  dagre.layout(g);

  const nodes: Node[] = rawNodes.map((n) => {
    const pos = g.node(n.id);
    const sz = NODE_SIZE[n.kind] || { w: 200, h: 70 };
    return {
      id: n.id,
      type: "kind",
      data: { label: n.label, kind: n.kind, description: n.description },
      position: { x: (pos?.x ?? 0) - sz.w / 2, y: (pos?.y ?? 0) - sz.h / 2 },
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
      width: sz.w,
      height: sz.h,
    };
  });

  const edges: Edge[] = rawEdges.map((e, i) => ({
    id: `e${i}-${e.from}-${e.to}`,
    source: e.from,
    target: e.to,
    label: e.relation,
    type: "smoothstep",
    animated: false,
    labelStyle: { fill: "var(--muted)", fontSize: 10 },
    labelBgStyle: { fill: "var(--panel-2)" },
    labelBgPadding: [3, 3] as [number, number],
    style: { stroke: "var(--border)", strokeWidth: 1.4 },
    markerEnd: { type: MarkerType.ArrowClosed, color: "var(--border)" },
  }));

  return { nodes, edges };
}

const KindNode = memo(({ data }: NodeProps<Node<{ label: string; kind: string; description?: string }>>) => {
  const color = KIND_COLOR[data.kind] || "#888";
  return (
    <div
      style={{
        background: "var(--panel-2)",
        border: `2px solid ${color}`,
        borderRadius: 8,
        padding: "8px 12px",
        boxShadow: "0 2px 8px rgba(0,0,0,0.3)",
        minWidth: 140,
        cursor: "pointer",
      }}
    >
      <Handle type="target" position={Position.Top} style={{ background: color, width: 6, height: 6 }} />
      <div style={{ fontSize: 10, fontWeight: 700, color, letterSpacing: 1 }}>
        {(KIND_LABEL[data.kind] || data.kind).toUpperCase()}
      </div>
      <div style={{ fontSize: 13, marginTop: 2, color: "var(--text)", lineHeight: 1.35 }}>
        {data.label}
      </div>
      <Handle type="source" position={Position.Bottom} style={{ background: color, width: 6, height: 6 }} />
    </div>
  );
});
KindNode.displayName = "KindNode";

export default function CausalFlowGraph({ graph, height = 560 }: {
  graph: { nodes: RawNode[]; edges: RawEdge[] };
  height?: number;
}) {
  const { nodes: laidNodes, edges: laidEdges } = useMemo(
    () => layout(graph?.nodes || [], graph?.edges || []),
    [graph],
  );
  const [selected, setSelected] = useState<RawNode | null>(null);

  const nodeTypes = useMemo(() => ({ kind: KindNode }), []);

  return (
    <div style={{
      width: "100%", height,
      background: "var(--panel-2)",
      borderRadius: 8,
      border: "1px solid var(--border)",
      overflow: "hidden",
    }}>
      <ReactFlow
        nodes={laidNodes}
        edges={laidEdges}
        nodeTypes={nodeTypes}
        onNodeClick={(_, node) => {
          const original = graph.nodes.find((n) => n.id === node.id);
          if (original) setSelected(original);
        }}
        fitView
        proOptions={{ hideAttribution: false }}
        minZoom={0.2}
        maxZoom={1.5}
      >
        <Controls showInteractive={false} />
        <MiniMap
          pannable zoomable
          nodeColor={(n) => KIND_COLOR[(n.data as any)?.kind] || "#666"}
          maskColor="rgba(14,16,21,0.7)"
          style={{ background: "var(--panel-2)" }}
        />
        <Background variant={BackgroundVariant.Dots} gap={16} size={1} color="var(--border)" />
      </ReactFlow>

      <Drawer
        title={selected ? `[${KIND_LABEL[selected.kind] || selected.kind}] ${selected.label}` : ""}
        placement="right"
        width={420}
        open={!!selected}
        onClose={() => setSelected(null)}
        mask={false}
      >
        {selected && (
          <div className="prose-cn">
            <Tag color={KIND_COLOR[selected.kind] || "default"} style={{ marginBottom: 12 }}>
              {KIND_LABEL[selected.kind] || selected.kind}
            </Tag>
            <Title level={5} style={{ marginTop: 0, color: "var(--text)" }}>
              {selected.label}
            </Title>
            {selected.description ? (
              <Paragraph style={{ color: "var(--text)", whiteSpace: "pre-wrap" }}>
                {selected.description}
              </Paragraph>
            ) : (
              <Text type="secondary">无更多描述</Text>
            )}
          </div>
        )}
      </Drawer>
    </div>
  );
}
