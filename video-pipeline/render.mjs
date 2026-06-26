// 墨析 · 解析视频 —— headless Chrome 逐帧捕获 + ffmpeg 编码(第 3 步,多视频)
// 用法:node render.mjs [video]    video 默认 architecture,另有 genome(读 specs.json 取 HTML)
// 借鉴 nexu-io/html-video 的 Hyperframes 范式,用本机系统 Chrome 跑通。
// 环境变量:CHROME 覆盖 Chrome 路径,FPS 覆盖帧率(默认 30)。
import puppeteer from "puppeteer-core";
import { execFileSync } from "node:child_process";
import { mkdirSync, rmSync, readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SPECS = JSON.parse(readFileSync(path.join(HERE, "specs.json"), "utf-8"));
const VIDEO = process.argv[2] || process.env.VIDEO || "architecture";
if (!SPECS[VIDEO]) { console.error("未知视频:", VIDEO); process.exit(1); }
const HTML = path.resolve(HERE, SPECS[VIDEO].html);
const FPS = Number(process.env.FPS || 30);
const BUILD = path.join(HERE, "_build", VIDEO);
const FRAMES = path.join(BUILD, "frames");
const OUT = path.join(BUILD, "silent.mp4");
const CHROME = process.env.CHROME || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

rmSync(FRAMES, { recursive: true, force: true });
mkdirSync(FRAMES, { recursive: true });

const browser = await puppeteer.launch({
  executablePath: CHROME, headless: "new",
  args: ["--headless=new", "--hide-scrollbars", "--force-color-profile=srgb", "--no-sandbox", "--font-render-hinting=none"],
  defaultViewport: { width: 1920, height: 1080, deviceScaleFactor: 1 },
});
const page = await browser.newPage();
await page.goto("file://" + HTML, { waitUntil: "networkidle0" });
await page.evaluate(async () => { if (document.fonts && document.fonts.ready) await document.fonts.ready; });
await page.waitForFunction("window.__ready===true", { timeout: 15000 });
const dur = await page.evaluate("window.__duration");
const total = Math.ceil(dur * FPS);
console.log(`[${VIDEO}] duration ${dur.toFixed(2)}s → ${total} frames @ ${FPS}fps`);

for (let f = 0; f < total; f++) {
  await page.evaluate((tt) => window.__seek(tt), f / FPS);
  await new Promise((r) => setTimeout(r, 8));
  await page.screenshot({ path: `${FRAMES}/f${String(f).padStart(5, "0")}.png`, clip: { x: 0, y: 0, width: 1920, height: 1080 } });
  if (f % 300 === 0) console.log("  frame", f, "/", total);
}
await browser.close();
console.log("frames done:", readdirSync(FRAMES).length);

execFileSync("ffmpeg", ["-y", "-framerate", String(FPS), "-i", `${FRAMES}/f%05d.png`,
  "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-movflags", "+faststart", OUT], { stdio: "inherit" });
console.log("silent MP4:", OUT);
