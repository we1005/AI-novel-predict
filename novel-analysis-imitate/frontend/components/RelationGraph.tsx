"use client";
import { useEffect, useMemo } from "react";
import {
  ReactFlow, Background, Controls, MarkerType,
  useNodesState, useEdgesState,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import dagre from "dagre";

const STATE_COLOR: Record<string, string> = {
  反目: "#c0392b", 背叛: "#c0392b", 宿敌: "#9c2c1f", 竞争: "#cf6b4a",
  结盟: "#2e6f80", 忠贞: "#2e7d5b", 师徒: "#9a6b2f", 亲情: "#2e7d5b",
  恋人: "#b8417a", 萍水: "#8a8270", 其他: "#8a8270",
};
const color = (s: string) => STATE_COLOR[s] || "#8a8270";

function build(tracks: Record<string, any[]>) {
  const deg: Record<string, number> = {};
  const rawEdges: any[] = [];
  Object.entries(tracks || {}).forEach(([pair, evs], i) => {
    const parts = pair.split(/\s*[—–-]\s*/);          // 容错各种破折号
    const a = parts[0], b = parts[1];
    if (!a || !b) return;
    deg[a] = (deg[a] || 0) + 1; deg[b] = (deg[b] || 0) + 1;
    const last = (evs && evs[evs.length - 1]) || {};
    const states = Array.from(new Set((evs || []).map((e: any) => e.state)));
    const c = color(last.state);
    rawEdges.push({
      id: `e${i}`, source: a, target: b, label: states.join("→"),
      labelStyle: { fill: "#211d16", fontSize: 11 },
      labelBgStyle: { fill: "#fbfaf4", fillOpacity: 0.9 },
      style: { stroke: c, strokeWidth: 1.6 },
      markerEnd: { type: MarkerType.ArrowClosed, color: c },
    });
  });
  const ids = Array.from(new Set(Object.keys(deg)));
  const maxDeg = Math.max(1, ...Object.values(deg));

  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "LR", ranksep: 90, nodesep: 26, edgesep: 16 });
  const W = (id: string) => Math.max(64, id.length * 15 + 24);
  ids.forEach((id) => g.setNode(id, { width: W(id), height: 38 }));
  rawEdges.forEach((e) => g.setEdge(e.source, e.target));
  try { dagre.layout(g); } catch { /* ignore */ }

  const nodes = ids.map((id) => {
    const p = g.node(id) || { x: 0, y: 0, width: W(id), height: 38 };
    const big = (deg[id] || 1) / maxDeg;
    return {
      id, data: { label: id },
      position: { x: (p.x || 0) - W(id) / 2, y: (p.y || 0) - 19 },
      width: W(id), height: 38,
      style: {
        width: W(id), height: 38, display: "flex", alignItems: "center", justifyContent: "center",
        background: "#fbfaf4", color: "#211d16",
        border: `1.5px solid ${big > 0.6 ? "#c0392b" : "#d6d0bf"}`,
        borderRadius: 3, fontSize: 12 + Math.round(big * 4),
        fontWeight: big > 0.4 ? 600 : 400, fontFamily: "var(--serif)",
      },
    };
  });
  return { nodes, edges: rawEdges };
}

export default function RelationGraph({ tracks, height = 560 }: { tracks: Record<string, any[]>; height?: number }) {
  const initial = useMemo(() => build(tracks), [tracks]);
  const [nodes, setNodes, onNodesChange] = useNodesState(initial.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initial.edges);

  // 书籍切换 / 数据更新时刷新图
  useEffect(() => { setNodes(initial.nodes); setEdges(initial.edges); }, [initial, setNodes, setEdges]);

  if (!initial.nodes.length) return <div className="empty">无关系数据</div>;
  return (
    <div style={{ height, border: "1px solid var(--rule-soft)", borderRadius: 2 }}>
      <ReactFlow
        nodes={nodes} edges={edges}
        onNodesChange={onNodesChange} onEdgesChange={onEdgesChange}
        fitView fitViewOptions={{ padding: 0.2 }}
        minZoom={0.05} maxZoom={2}
        onInit={(inst) => setTimeout(() => inst.fitView({ padding: 0.2 }), 60)}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#e6e1d1" gap={20} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
