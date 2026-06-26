"use client";
import { useMemo } from "react";
import { ReactFlow, Background, Controls, MarkerType } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import dagre from "dagre";

// 关系状态 → 颜色(对立=朱砂,亲密=石青/绿,中性=灰)
const STATE_COLOR: Record<string, string> = {
  反目: "#c0392b", 背叛: "#c0392b", 宿敌: "#9c2c1f", 竞争: "#cf6b4a",
  结盟: "#2e6f80", 忠贞: "#2e7d5b", 师徒: "#9a6b2f", 亲情: "#2e7d5b",
  恋人: "#b8417a", 萍水: "#8a8270", 其他: "#8a8270",
};
const color = (s: string) => STATE_COLOR[s] || "#8a8270";

function layout(nodes: any[], edges: any[]) {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "LR", ranksep: 90, nodesep: 28, edgesep: 18 });
  for (const n of nodes) {
    const w = Math.max(64, (n.data.label.length * 15) + 24);
    g.setNode(n.id, { width: w, height: 38 });
  }
  for (const e of edges) g.setEdge(e.source, e.target);
  dagre.layout(g);
  return {
    nodes: nodes.map((n) => {
      const p = g.node(n.id);
      return { ...n, position: { x: p.x - p.width / 2, y: p.y - p.height / 2 },
               style: { ...n.style, width: p.width } };
    }),
    edges,
  };
}

export default function RelationGraph({ tracks, height = 560 }: { tracks: Record<string, any[]>; height?: number }) {
  const { nodes, edges } = useMemo(() => {
    const deg: Record<string, number> = {};
    const rawEdges: any[] = [];
    Object.entries(tracks || {}).forEach(([pair, evs], i) => {
      const [a, b] = pair.split(" — ");
      if (!a || !b) return;
      deg[a] = (deg[a] || 0) + 1; deg[b] = (deg[b] || 0) + 1;
      const last = evs[evs.length - 1] || {};
      const states = Array.from(new Set(evs.map((e: any) => e.state)));
      const c = color(last.state);
      rawEdges.push({
        id: `e${i}`, source: a, target: b,
        label: states.join("→"),
        labelStyle: { fill: "#211d16", fontSize: 11, fontFamily: "var(--mono)" },
        labelBgStyle: { fill: "#fbfaf4", fillOpacity: 0.9 },
        style: { stroke: c, strokeWidth: 1.6 },
        markerEnd: { type: MarkerType.ArrowClosed, color: c },
      });
    });
    const ids = Array.from(new Set(Object.keys(deg)));
    const maxDeg = Math.max(1, ...Object.values(deg));
    const rawNodes = ids.map((id) => {
      const big = (deg[id] || 1) / maxDeg;
      return {
        id, data: { label: id }, position: { x: 0, y: 0 },
        style: {
          background: "#fbfaf4", color: "#211d16",
          border: `1.5px solid ${big > 0.6 ? "#c0392b" : "#d6d0bf"}`,
          borderRadius: 3, fontSize: 12 + Math.round(big * 4),
          fontWeight: big > 0.4 ? 600 : 400, padding: "6px 4px", textAlign: "center" as const,
          fontFamily: "var(--serif)",
        },
      };
    });
    return layout(rawNodes, rawEdges);
  }, [tracks]);

  if (!nodes.length) return <div className="empty">无关系数据</div>;
  return (
    <div style={{ height, border: "1px solid var(--rule-soft)", borderRadius: 2 }}>
      <ReactFlow nodes={nodes} edges={edges} fitView minZoom={0.1} proOptions={{ hideAttribution: true }}>
        <Background color="#e6e1d1" gap={20} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
