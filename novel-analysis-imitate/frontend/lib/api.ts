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
};
