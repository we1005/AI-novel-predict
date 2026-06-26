"use client";
import { usePathname } from "next/navigation";
import Link from "next/link";

export default function Nav() {
  const p = usePathname();
  const items = [
    { href: "/", t: "深度分析" },
    { href: "/generate", t: "仿写/重组生成" },
  ];
  return (
    <div style={{ borderBottom: "1px solid var(--border)", background: "var(--panel)" }}>
      <div className="wrap" style={{ padding: "12px 20px", display: "flex", gap: 18, alignItems: "center" }}>
        <b style={{ fontSize: 15 }}>墨析</b>
        {items.map((it) => (
          <Link key={it.href} href={it.href}
            style={{ color: p === it.href ? "var(--accent)" : "var(--muted)", fontWeight: p === it.href ? 700 : 400 }}>
            {it.t}
          </Link>
        ))}
      </div>
    </div>
  );
}
