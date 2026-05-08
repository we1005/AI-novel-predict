import { NextResponse } from "next/server";
import fs from "node:fs/promises";
import path from "node:path";

export const dynamic = "force-dynamic";

// Resolved at runtime — the docs folder sits next to /frontend, /backend.
function docsDir() {
  return path.join(process.cwd(), "..", "墨笔-agent架构设计docs");
}

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const file = searchParams.get("file");

  try {
    if (!file) {
      const dir = docsDir();
      const entries = await fs.readdir(dir);
      const mds = entries.filter((f) => f.endsWith(".md")).sort();
      return NextResponse.json({ files: mds });
    }
    if (file.includes("..") || file.includes("/")) {
      return NextResponse.json({ error: "invalid file" }, { status: 400 });
    }
    const full = path.join(docsDir(), file);
    const content = await fs.readFile(full, "utf-8");
    return NextResponse.json({ file, content });
  } catch (e: any) {
    return NextResponse.json({ error: String(e?.message || e) }, { status: 404 });
  }
}
