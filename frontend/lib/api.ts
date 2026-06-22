// Hit backend directly. Next.js's `rewrites()` proxy hangs up sockets after
// ~60-120s, which kills long endpoints (e.g. /predict/arc/run takes 90-120s
// with the macro-schema). Backend CORS already allows http://localhost:3100.
const BASE =
  (typeof window !== "undefined" && (window as any).__BACKEND_URL__) ||
  process.env.NEXT_PUBLIC_BACKEND_URL ||
  "http://localhost:8000";

async function j<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(BASE + url, {
    ...init,
    headers: { "content-type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

export const api = {
  health: () => j<{ ok: boolean }>("/health"),

  splitCorpus: (path?: string) =>
    j<{ chapters: number; total_chars: number }>(
      "/ingest/split",
      { method: "POST", body: JSON.stringify(path ? { path } : {}) }
    ),
  chapterCount: () =>
    j<{ total: number; first: number; last: number }>("/ingest/chapters/count"),
  startExtract: (start: number, end: number) =>
    j<unknown>(`/ingest/extract?start=${start}&end=${end}`, { method: "POST" }),
  startExtractAll: (batchSize: number = 50, workers: number = 2) =>
    j<{ queued: number; skipped_done: number; skipped_running: number; batch_size: number; workers: number; first: number; last: number; ranges_queued: number[][]; msg?: string }>(
      `/ingest/extract/all?batch_size=${batchSize}&workers=${workers}`,
      { method: "POST" }
    ),
  cleanupStuckBatches: (olderThanMinutes: number = 30) =>
    j<{ cleaned: number; items: any[]; older_than_minutes: number }>(
      "/ingest/batches/cleanup-stuck",
      { method: "POST", body: JSON.stringify({ older_than_minutes: olderThanMinutes }) }
    ),
  retryBatch: (batchId: number) =>
    j<{
      id: number;
      action: "superseded" | "retrying";
      range: [number, number];
      covered_chapters: number;
      gap_chapters: number[];
      gap_total?: number;
      msg?: string;
    }>(`/ingest/batches/${batchId}/retry`, { method: "POST" }),
  extractionCoverage: () =>
    j<{
      first: number;
      last: number;
      total: number;
      covered: number;
      missing: number[];
      missing_ranges: [number, number][];
    }>("/ingest/coverage"),
  batches: () => j<any[]>("/ingest/batches"),

  entities: (params?: { type?: string; search?: string }) => {
    const qs = new URLSearchParams();
    if (params?.type) qs.set("type", params.type);
    if (params?.search) qs.set("search", params.search);
    return j<any[]>(`/memory/entities?${qs}`);
  },
  foreshadowings: (status: string = "open") =>
    j<any[]>(`/memory/foreshadowings?status=${status}`),
  rules: () => j<any[]>("/memory/rules"),
  plot: (minImportance: number = 50) =>
    j<any[]>(`/memory/plot?min_importance=${minImportance}`),

  graphCharacters: (upTo?: number, topN?: number) => {
    const qs = new URLSearchParams();
    if (topN != null) qs.set("top_n", String(topN));
    if (upTo != null) qs.set("up_to_chapter", String(upTo));
    const q = qs.toString();
    return j<{ nodes: any[]; edges: any[] }>(`/graph/characters${q ? `?${q}` : ""}`);
  },
  graphForeshadowings: (upTo?: number) =>
    j<{ items: any[] }>(
      `/graph/foreshadowings${upTo != null ? `?up_to_chapter=${upTo}` : ""}`
    ),
  hero: () => j<any>("/graph/hero"),
  heroItems: () => j<any>("/graph/hero-items"),
  // ----- Sim / Profile / Interview / Multi-agent simulation -----
  profilesList: () => j<any[]>("/sim/profiles"),
  profileGet: (entityId: number) => j<any>(`/sim/profiles/${entityId}`),
  profilesRebuild: (params: { top_n?: number; after_chapter?: number | null; entity_ids?: number[] | null } = {}) =>
    j<any>("/sim/profiles/rebuild", { method: "POST", body: JSON.stringify(params) }),

  interviewStream: async (params: { character_id: number; after_chapter: number; question: string }, onChunk: (s: string) => void) => {
    const r = await fetch(BASE + "/sim/interview", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(params),
    });
    if (!r.ok || !r.body) throw new Error(`${r.status}`);
    const reader = r.body.getReader();
    const dec = new TextDecoder();
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      onChunk(dec.decode(value));
    }
  },
  interviewHistory: (characterId?: number, limit: number = 50) => {
    const qs = new URLSearchParams();
    if (characterId != null) qs.set("character_id", String(characterId));
    qs.set("limit", String(limit));
    return j<any[]>(`/sim/interview/history?${qs}`);
  },

  simulate: (params: { after_chapter: number; n_rounds?: number; n_characters?: number; focus_characters?: number[]; user_hints?: string }) =>
    j<any>("/sim/simulate", { method: "POST", body: JSON.stringify(params) }),
  simulationsList: () => j<any[]>("/sim/simulate/runs"),
  simulationGet: (id: number) => j<any>(`/sim/simulate/runs/${id}`),

  extractRelationships: (topN: number = 50) =>
    j<{ roles_assigned: number; relationships: number; cost_usd: number; elapsed_ms: number }>(
      `/graph/relationships/extract?top_n=${topN}`,
      { method: "POST" },
    ),
  relationships: () => j<any[]>("/graph/relationships"),
  graphDedup: () =>
    j<{ candidates: number; confirmed: number; merged: number; errors: number }>(
      "/graph/dedup", { method: "POST" }),
  graphRecomputeImportance: () =>
    j<{ updated: number }>("/graph/recompute-importance", { method: "POST" }),
  timeline: (minImportance?: number) =>
    j<any[]>(`/graph/timeline${minImportance != null ? `?min_importance=${minImportance}` : ""}`),

  predictRun: (afterChapter: number, candidates: number = 5) =>
    j<any>("/predict/run", {
      method: "POST",
      body: JSON.stringify({ after_chapter: afterChapter, candidates }),
    }),
  predictList: () => j<any[]>("/predict/runs"),
  predictGet: (id: number) => j<any>(`/predict/runs/${id}`),
  predictWrite: async (runId: number, idx: number, onChunk: (s: string) => void) => {
    const r = await fetch(BASE + "/predict/write", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ run_id: runId, chosen_index: idx }),
    });
    if (!r.ok || !r.body) throw new Error(`${r.status}`);
    const reader = r.body.getReader();
    const dec = new TextDecoder();
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      onChunk(dec.decode(value));
    }
  },

  monitorSummary: (hours: number = 168) =>
    j<any>(`/monitor/summary?hours=${hours}`),
  monitorRecent: (limit: number = 50) =>
    j<any[]>(`/monitor/recent?limit=${limit}`),

  mysteries: () => j<any[]>("/mysteries"),
  mysteriesRebuild: (skipExisting: boolean = false) =>
    j<{ batches_processed: number; batches_failed: number; mysteries_total: number; cost_usd: number; elapsed_s: number; per_batch: any[] }>(
      "/mysteries/rebuild",
      { method: "POST", body: JSON.stringify({ skip_existing: skipExisting }) },
    ),
  mysteryDelete: (id: number) => j<{ ok: true }>(`/mysteries/${id}`, { method: "DELETE" }),
  mysteryNote: (id: number, note: string) =>
    j<{ ok: true }>(`/mysteries/${id}`, { method: "PATCH", body: JSON.stringify({ note }) }),

  outlineRefine: (params: {
    source_kind: "arc" | "predict";
    source_run_id: number;
    chosen_index: number;
    phase_index?: number | null;
    user_hints?: string;
  }) => j<any>("/outline/refine", { method: "POST", body: JSON.stringify(params) }),
  outlineList: () => j<any[]>("/outline/runs"),
  outlineGet: (id: number) => j<any>(`/outline/runs/${id}`),
  outlinePatchChapter: (runId: number, chapterIndex: number, patch: any) =>
    j<{ ok: true }>(`/outline/runs/${runId}/chapters/${chapterIndex}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),

  draftWrite: (outlineRunId: number, chapterIndex: number, opts: { skip_reviews?: boolean; max_attempts?: number } = {}) =>
    j<any>("/draft/write", {
      method: "POST",
      body: JSON.stringify({
        outline_run_id: outlineRunId,
        chapter_index: chapterIndex,
        skip_reviews: !!opts.skip_reviews,
        max_attempts: opts.max_attempts ?? 3,
      }),
    }),
  draftList: () => j<any[]>("/draft/drafts"),
  draftGet: (id: number) => j<any>(`/draft/drafts/${id}`),
  draftPatchText: (id: number, text: string) =>
    j<{ ok: true }>(`/draft/drafts/${id}`, { method: "PATCH", body: JSON.stringify({ text }) }),

  // ----- Books / Library -----
  booksList: () => j<any>("/books"),
  booksScan: () => j<any>("/books/scan", { method: "POST" }),
  booksImport: (filename: string, title?: string, setActive: boolean = true) =>
    j<any>("/books/import", {
      method: "POST",
      body: JSON.stringify({ filename, title, set_active: setActive }),
    }),
  booksSetActive: (slug: string) =>
    j<any>("/books/active", { method: "PUT", body: JSON.stringify({ slug }) }),
  booksDelete: (slug: string) =>
    j<any>(`/books/${encodeURIComponent(slug)}`, { method: "DELETE" }),

  // ----- Style (author voice analysis) -----
  styleGet: () => j<any>("/style"),
  styleAnalyze: (sampleN: number = 8) =>
    j<any>("/style/analyze", { method: "POST", body: JSON.stringify({ sample_n: sampleN }) }),
  styleToggle: (payload: { mimic_enabled?: boolean; bilingual?: boolean }) =>
    j<any>("/style/toggle", { method: "PUT", body: JSON.stringify(payload) }),
  bilingualStart: (payload: { brief: string; after_chapter: number; chapter_n?: number }) =>
    j<any>("/style/bilingual", { method: "POST", body: JSON.stringify(payload) }),
  bilingualList: () => j<any[]>("/style/bilingual"),
  bilingualGet: (id: number) => j<any>(`/style/bilingual/${id}`),
  revoiceStart: (payload: { voice: string; source_chapter?: number; text?: string }) =>
    j<any>("/style/revoice", { method: "POST", body: JSON.stringify(payload) }),
  revoiceList: () => j<any[]>("/style/revoice"),
  revoiceGet: (id: number) => j<any>(`/style/revoice/${id}`),

  // ----- Settings -----
  settingsGet: () => j<any>("/settings"),
  settingsPut: (payload: any) =>
    j<any>("/settings", { method: "PUT", body: JSON.stringify(payload) }),
  settingsReset: () => j<any>("/settings/reset", { method: "POST" }),
  settingsTestKey: (payload: { api_key?: string; base_url?: string; model?: string; provider?: string } = {}) =>
    j<any>("/settings/test-key", { method: "POST", body: JSON.stringify(payload) }),

  arcRun: (afterChapter: number, nCandidates: number = 3, targetChapters: number = 100, userHints: string = "") =>
    j<any>("/predict/arc/run", {
      method: "POST",
      body: JSON.stringify({
        after_chapter: afterChapter,
        n_candidates: nCandidates,
        target_chapters: targetChapters,
        user_hints: userHints,
      }),
    }),
  arcList: () => j<any[]>("/predict/arc/runs"),
  arcGet: (id: number) => j<any>(`/predict/arc/runs/${id}`),
  // 整本故事弧推演 (whole-book projection)
  arcProject: (runId: number, chosenIndex: number) =>
    j<any>(`/predict/arc/runs/${runId}/project`, { method: "POST", body: JSON.stringify({ chosen_index: chosenIndex }) }),
  projectionList: () => j<any[]>("/predict/projections"),
  projectionGet: (id: number) => j<any>(`/predict/projections/${id}`),
};
