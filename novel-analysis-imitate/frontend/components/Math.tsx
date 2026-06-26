"use client";
import katex from "katex";
import "katex/dist/katex.min.css";

export function M({ children }: { children: string }) {
  const html = katex.renderToString(children, { throwOnError: false, displayMode: false });
  return <span dangerouslySetInnerHTML={{ __html: html }} />;
}

export function MB({ children }: { children: string }) {
  const html = katex.renderToString(children, { throwOnError: false, displayMode: true });
  return <div style={{ margin: "10px 0", overflowX: "auto" }} dangerouslySetInnerHTML={{ __html: html }} />;
}
