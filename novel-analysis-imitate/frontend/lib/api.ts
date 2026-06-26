// naimitate 前端 API 层。经 next rewrites 同源代理到后端 :8100。
async function j(path: string, init?: RequestInit) {
  const r = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!r.ok) throw new Error(`${path} -> ${r.status}`);
  return r.json();
}

export const api = {
  books: () => j("/books"),
  analysis: (slug: string) => j(`/books/${encodeURIComponent(slug)}/analysis`),
  analyzeBook: (slug: string, body: { layers?: string[]; max_chapters?: number }) =>
    j(`/books/${encodeURIComponent(slug)}/analyze`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  speedread: (slug: string) => j(`/books/${encodeURIComponent(slug)}/speedread`),
  runSpeedread: (slug: string) =>
    j(`/books/${encodeURIComponent(slug)}/speedread`, { method: "POST", body: JSON.stringify({}) }),
  // ---- 生成(Phase 2+)----
  composeList: () => j("/compose"),
  uc2: (body: any) => j("/compose/uc2", { method: "POST", body: JSON.stringify(body) }),
  uc1: (body: any) => j("/compose/uc1", { method: "POST", body: JSON.stringify(body) }),
  uc3: (body: any) => j("/compose/uc3", { method: "POST", body: JSON.stringify(body) }),
  uc4: (body: any) => j("/compose/uc4", { method: "POST", body: JSON.stringify(body) }),
  generate: (cslug: string, chapter_index: number, skip_reviews = false) =>
    j(`/compose/${encodeURIComponent(cslug)}/generate`, {
      method: "POST", body: JSON.stringify({ chapter_index, skip_reviews }),
    }),
  exportCompose: (cslug: string) => j(`/compose/${encodeURIComponent(cslug)}/export`),
};
