"use client";
import { useEffect, useId, useRef, useState } from "react";

let _inited = false;

/** 客户端渲染一段 mermaid 定义为 SVG。动态 import,避免拖慢首屏。 */
export default function Mermaid({ chart, title }: { chart: string; title?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const rid = useId().replace(/[^a-zA-Z0-9]/g, "");
  const [err, setErr] = useState("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const mermaid = (await import("mermaid")).default;
        if (!_inited) {
          mermaid.initialize({
            startOnLoad: false,
            theme: "neutral",
            securityLevel: "loose",
            flowchart: { htmlLabels: true, curve: "basis" },
            fontFamily: "inherit",
          });
          _inited = true;
        }
        const { svg } = await mermaid.render("mmd" + rid, chart);
        if (!cancelled && ref.current) ref.current.innerHTML = svg;
      } catch (e: any) {
        if (!cancelled) setErr(String(e?.message || e));
      }
    })();
    return () => { cancelled = true; };
  }, [chart, rid]);

  return (
    <div style={{ margin: "8px 0 18px" }}>
      {title && <div style={{ fontSize: 13, fontWeight: 600, color: "var(--zhe,#9a6b2f)", marginBottom: 6 }}>{title}</div>}
      {err ? (
        <pre style={{ whiteSpace: "pre-wrap", fontSize: 12, color: "#c0392b", background: "var(--paper,#f1efe5)", padding: 10, borderRadius: 6 }}>
          mermaid 渲染失败:{err}
          {"\n\n"}{chart}
        </pre>
      ) : (
        <div ref={ref} style={{ overflowX: "auto", background: "var(--paper-2,#faf8f0)", border: "1px solid var(--rule,#d6d0bf)", borderRadius: 8, padding: 14, textAlign: "center" }} />
      )}
    </div>
  );
}
