// 墨析 · 解析视频 —— 时间轴快速校验(可选,多视频)
// 用法:node check.mjs [video] [t1 t2 ...]   抽帧到 _build/<video>/check_*.png
import puppeteer from "puppeteer-core";
import path from "node:path";
import { mkdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SPECS = JSON.parse(readFileSync(path.join(HERE, "specs.json"), "utf-8"));
const VIDEO = process.argv[2] || process.env.VIDEO || "architecture";
if (!SPECS[VIDEO]) { console.error("未知视频:", VIDEO); process.exit(1); }
const HTML = path.resolve(HERE, SPECS[VIDEO].html);
const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const BUILD = path.join(HERE, "_build", VIDEO);
mkdirSync(BUILD, { recursive: true });
const customTimes = process.argv.slice(3).map(Number).filter((x) => !Number.isNaN(x));

const b = await puppeteer.launch({
  executablePath: CHROME, headless: "new",
  args: ["--headless=new", "--no-sandbox", "--hide-scrollbars", "--force-color-profile=srgb", "--font-render-hinting=none"],
  defaultViewport: { width: 1920, height: 1080, deviceScaleFactor: 1 },
});
const pg = await b.newPage();
const errs = [];
pg.on("pageerror", (e) => errs.push(String(e)));
pg.on("console", (m) => { if (m.type() === "error") errs.push("console:" + m.text()); });
await pg.goto("file://" + HTML, { waitUntil: "networkidle0" });
try { await pg.waitForFunction("window.__ready===true", { timeout: 8000 }); }
catch (e) { console.log("__ready 未就绪! 错误:", errs.slice(0, 5)); await b.close(); process.exit(1); }
const dur = await pg.evaluate("window.__duration");
console.log(`[${VIDEO}] __duration = ${dur.toFixed(2)}s   pageerrors: ${errs.length}`);
const times = customTimes.length ? customTimes : [7, dur * 0.35, dur * 0.6, dur * 0.85, Math.max(0, dur - 1)];
for (const t of times) {
  await pg.evaluate((tt) => window.__seek(tt), t);
  await new Promise((r) => setTimeout(r, 25));
  await pg.screenshot({ path: `${BUILD}/check_${Math.round(t)}.png`, clip: { x: 0, y: 0, width: 1920, height: 1080 } });
}
if (errs.length) console.log("ERR:", errs.slice(0, 5));
await b.close();
