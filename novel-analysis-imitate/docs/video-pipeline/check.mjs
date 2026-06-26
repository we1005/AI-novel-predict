// 墨析 · 架构解析视频 —— 时间轴快速校验(可选)
//
// 加载 architecture-video.html,确认 window.__ready / __duration 正常、无 pageerror,
// 并在几个时刻各抽一帧到 _build/check_*.png 供肉眼核对。全量渲染前先跑这个最省时。
// 用法:node check.mjs [HTML]
import puppeteer from "puppeteer-core";
import path from "node:path";
import { mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const HTML = path.resolve(process.argv[2] || path.join(HERE, "..", "architecture-video.html"));
const CHROME = process.env.CHROME ||
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const BUILD = path.join(HERE, "_build");
mkdirSync(BUILD, { recursive: true });

const b = await puppeteer.launch({
  executablePath: CHROME, headless: "new",
  args: ["--headless=new", "--no-sandbox", "--hide-scrollbars",
         "--force-color-profile=srgb", "--font-render-hinting=none"],
  defaultViewport: { width: 1920, height: 1080, deviceScaleFactor: 1 },
});
const pg = await b.newPage();
const errs = [];
pg.on("pageerror", (e) => errs.push(String(e)));
pg.on("console", (m) => { if (m.type() === "error") errs.push("console:" + m.text()); });
await pg.goto("file://" + HTML, { waitUntil: "networkidle0" });
try {
  await pg.waitForFunction("window.__ready===true", { timeout: 8000 });
} catch (e) {
  console.log("__ready 未就绪! 错误:", errs.slice(0, 5));
  await b.close(); process.exit(1);
}
const dur = await pg.evaluate("window.__duration");
console.log("__duration =", dur.toFixed(2), "s   pageerrors:", errs.length);
for (const t of [7, 40, 75, 110, Math.max(0, dur - 1)]) {
  await pg.evaluate((tt) => window.__seek(tt), t);
  await new Promise((r) => setTimeout(r, 20));
  await pg.screenshot({ path: `${BUILD}/check_${Math.round(t)}.png`,
                        clip: { x: 0, y: 0, width: 1920, height: 1080 } });
}
if (errs.length) console.log("ERR:", errs.slice(0, 5));
await b.close();
