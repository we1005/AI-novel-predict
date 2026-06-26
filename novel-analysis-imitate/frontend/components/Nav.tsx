"use client";
import { usePathname } from "next/navigation";
import Link from "next/link";

export default function Nav() {
  const p = usePathname();
  const items = [
    { href: "/", t: "深度分析" },
    { href: "/generate", t: "仿写 · 重组" },
  ];
  return (
    <div className="masthead">
      <div className="masthead-in">
        <span className="seal">墨析</span>
        <span style={{ flex: 1 }} />
        {items.map((it) => (
          <Link key={it.href} href={it.href} className="navlink"
            style={{
              color: p === it.href ? "var(--zhu-soft)" : "var(--muted)",
              borderBottom: p === it.href ? "2px solid var(--zhu)" : "2px solid transparent",
            }}>
            {it.t}
          </Link>
        ))}
      </div>
    </div>
  );
}
