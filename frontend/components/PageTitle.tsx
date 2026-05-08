"use client";

import { useTheme } from "./ThemeProvider";

/**
 * Unified page heading. In modern theme uses the decorative Chinese font
 * (Ma Shan Zheng) for the title and a serif subtitle. In classic theme falls
 * back to a plain h1.
 *
 * Usage:
 *   <PageTitle title="大纲" subtitle="..." />
 *
 * If `title` is omitted the rendering falls back to the page-specific text
 * already in the layout (no-op shell).
 */
export default function PageTitle({
  title,
  subtitle,
}: {
  title?: string;
  subtitle?: string;
}) {
  const { theme } = useTheme();

  if (theme !== "modern") {
    return (
      <>
        {title && <h1>{title}</h1>}
        {subtitle && <p className="muted" style={{ marginTop: -6 }}>{subtitle}</p>}
      </>
    );
  }

  return (
    <div style={{ marginBottom: 18 }}>
      {title && (
        <h1 style={{
          fontFamily: "var(--decorative)",
          fontSize: 36,
          letterSpacing: 4,
          color: "var(--accent-2)",
          margin: 0,
          fontWeight: 400,
        }}>
          {title}
        </h1>
      )}
      {subtitle && (
        <p style={{
          fontFamily: "var(--serif)",
          fontSize: 13, color: "var(--muted)",
          margin: title ? "4px 0 0" : 0,
          letterSpacing: 1,
        }}>
          {subtitle}
        </p>
      )}
    </div>
  );
}
