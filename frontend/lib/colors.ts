/**
 * Read live CSS variable values so chart libraries (ECharts, Cytoscape) can
 * pick up the current color scheme without each chart needing to import the
 * theme provider.
 *
 * Always call this inside an effect/handler — it reads the DOM. Pair with a
 * ``colorScheme`` dep on the effect so the chart re-initializes on toggle.
 */
export function cssVar(name: string, fallback: string = ""): string {
  if (typeof window === "undefined") return fallback;
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

export function chartPalette() {
  return {
    bg: cssVar("--panel-2", "#1f232f"),
    panel: cssVar("--panel", "#161922"),
    text: cssVar("--text", "#e8eaef"),
    muted: cssVar("--muted", "#8a92a3"),
    border: cssVar("--border", "#2a2f3d"),
    accent: cssVar("--accent", "#7aa2f7"),
    accent2: cssVar("--accent-2", "#bb9af7"),
    good: cssVar("--good", "#9ece6a"),
    warn: cssVar("--warn", "#faad14"),
    bad: cssVar("--bad", "#f7768e"),
    cStory: cssVar("--c-story", "#1890ff"),
    cWorld: cssVar("--c-world", "#52c41a"),
    cForeshadow: cssVar("--c-foreshadow", "#faad14"),
    cSubplot: cssVar("--c-subplot", "#b37feb"),
    cCharacter: cssVar("--c-character", "#5b8c00"),
    cMystery: cssVar("--c-mystery", "#bb9af7"),
  };
}
