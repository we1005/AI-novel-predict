# 墨笔 · 产品介绍页(工程化版 landing-app)

用**成熟前端组件体系**重建的墨笔落地页,栈与孪生站「玄鉴」完全对齐:

> **Vue 3 + Vite + Tailwind v4 + reka-ui(shadcn-vue)+ cva/clsx/tailwind-merge + @vueuse/motion + lucide-vue-next**

与仓库根目录的 `landing/index.html`(零构建单文件版)是**两套并存**:单文件版可直接 `open` 免安装;这一版是可维护、可复用组件的工程化版本。

## 跑起来

```bash
cd landing-app
npm install          # 若 NODE_OPTIONS 报错:env -u NODE_OPTIONS npm install
npm run dev          # 开发,默认 http://localhost:5173
npm run build        # 产物 dist/
npm run preview      # 预览 dist,端口 4180
```

部署(Netlify):`netlify deploy --prod --dir=landing-app/dist`,或连 GitHub 自动构建(`netlify.toml` 已写好 base/command/publish)。

## 用了哪些"成熟组件"(回应「是不是裸 CSS」)

| 关注点 | 方案 |
| --- | --- |
| 组件底座 | **reka-ui** 的 `Primitive`(= Radix-for-Vue,shadcn-vue 的底座) |
| 变体系统 | **class-variance-authority(cva)** 定义 Button/Badge 变体 |
| class 合并 | **clsx + tailwind-merge** → `cn()`(`src/lib/utils.ts`) |
| 样式引擎 | **Tailwind v4**(`@tailwindcss/vite`,`@theme` 设计 token) |
| 动效 | **@vueuse/motion**(`v-motion` + `visible-once` 滚动揭幕)+ rAF 视差 + IntersectionObserver count-up |
| 图标 | **lucide-vue-next** |
| 字体 | LXGW 霞鹜文楷(CJK)+ Noto Serif SC(拉丁),`unicode-range` 逐字符分流 |

`src/components/ui/{button,badge}` 就是标准 shadcn-vue 组件写法(`Component.vue` + `variants.ts` + `index.ts`),整页 CTA / 徽章都走它们。

## 结构

```
landing-app/
├─ index.html                 入口(字体 <link> + #app)
├─ vite.config.ts             vue + tailwindcss 插件
├─ netlify.toml               部署配置
└─ src/
   ├─ main.ts                 createApp + MotionPlugin
   ├─ App.vue → views/home/HomePage.vue
   ├─ assets/tailwind.css     @theme 设计 token(墨/花青/朱砂)
   ├─ style/home.css          签名样式:混排字体、毛玻璃、朱文印、竖排双墨、揭幕、水印
   ├─ brand.ts                品牌与文案 + Proof 数字单点
   ├─ lib/utils.ts            cn()
   ├─ components/ui/          shadcn-vue:button / badge
   └─ views/home/
      ├─ HomePage.vue         组合各 section + 全页水印视差
      └─ sections/            NavBar / Hero / Argue / Proof / Pipeline / Footer
```

## 设计语言(与玄鉴同调,保留墨笔魂)

- 暖白宣纸 `#faf7f2` + 浓墨 `#14141a` + 花青(续写)`#2e6b75` + 朱砂印 `#b4361a`。
- 主视觉:巨字命题「记忆 > 上下文」+ 竖排**双墨接笔**手稿(原著墨→朱文印「此後·墨筆續」→花青续写)。
- 节奏:亮(Hero/Argue)→ 暗(Proof · count-up)→ 亮(Pipeline)→ 暗(Footer 题签),明暗交替。
- 内容取自真实交付:《天之炽》157→260、58.5 万字、104 章、21 agent、4 层记忆。
- 可访问性:响应式(桌面双列 / 移动单列,手稿转横排)、`prefers-reduced-motion` 尊重、focus-visible 花青描边。
