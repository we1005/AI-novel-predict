// 墨析 · 架构解析视频 —— headless Chrome 逐帧捕获 + ffmpeg 编码(第 3 步)
//
// 把时间驱动的 architecture-video.html(暴露 window.__seek/__duration/__ready)
// 逐帧定格截图,再用 ffmpeg(libx264)编成无声 MP4。
// 借鉴 nexu-io/html-video 的 Hyperframes 渲染范式,但直接用本机系统 Chrome 跑通。
//
// 依赖:puppeteer-core(见 package.json,先 `npm install`)、ffmpeg、本机 Chrome。
// 用法:node render.mjs [HTML] [OUT.mp4]
//   默认 HTML = ../architecture-video.html,OUT = ./_build/silent.mp4
// 环境变量:CHROME 覆盖 Chrome 可执行路径,FPS 覆盖帧率(默认 30)。
import puppeteer from "puppeteer-core";
import { execFileSync } from "node:child_process";
import { mkdirSync, rmSync, readdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const HTML = path.resolve(process.argv[2] || path.join(HERE, "..", "architecture-video.html"));
const OUT = path.resolve(process.argv[3] || path.join(HERE, "_build", "silent.mp4"));
const FPS = Number(process.env.FPS || 30);
const FRAMES = path.join(HERE, "_build", "frames");
const CHROME = process.env.CHROME ||
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"; // macOS 默认

rmSync(FRAMES, { recursive: true, force: true });
mkdirSync(FRAMES, { recursive: true });

const browser = await puppeteer.launch({
  executablePath: CHROME, headless: "new",
  args: ["--headless=new", "--hide-scrollbars", "--force-color-profile=srgb",
         "--no-sandbox", "--font-render-hinting=none"],
  defaultViewport: { width: 1920, height: 1080, deviceScaleFactor: 1 },
});
const page = await browser.newPage();
await page.goto("file://" + HTML, { waitUntil: "networkidle0" });
await page.evaluate(async () => { if (document.fonts && document.fonts.ready) await document.fonts.ready; });
await page.waitForFunction("window.__ready===true", { timeout: 15000 });
const dur = await page.evaluate("window.__duration");
const total = Math.ceil(dur * FPS);
console.log("duration", dur.toFixed(2), "s →", total, "frames @", FPS, "fps");

for (let f = 0; f < total; f++) {
  const t = f / FPS;
  await page.evaluate((tt) => window.__seek(tt), t);   // 单调递增 seek:回调/进度条按序触发
  await new Promise((r) => setTimeout(r, 8));            // 让 DOM/SVG 刷新一帧
  await page.screenshot({ path: `${FRAMES}/f${String(f).padStart(5, "0")}.png`,
                          clip: { x: 0, y: 0, width: 1920, height: 1080 } });
  if (f % 300 === 0) console.log("  frame", f, "/", total);
}
await browser.close();
console.log("frames done:", readdirSync(FRAMES).length);

execFileSync("ffmpeg", ["-y", "-framerate", String(FPS), "-i", `${FRAMES}/f%05d.png`,
  "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-movflags", "+faststart", OUT],
  { stdio: "inherit" });
console.log("silent MP4:", OUT);
