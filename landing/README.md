# 墨笔 · 产品介绍页(landing)

可托管的**单文件**介绍页,对外讲清"墨笔靠先建结构化记忆(读者的大脑)续写百万字长篇"。
浅色编辑风,参照孪生站「玄鉴」的落地页体系(暖白 + 霞鹜文楷 + 巨字/水印/浅玻璃)重做。

- **打开**:`open landing/index.html`(或丢 Netlify / GitHub Pages 静态托管)。
- **风格**:暖白 `#FAFAF7` + 墨黑 + 朱砂印 `#B4361A` + 花青(续写)。
- **字体(成熟网络字体,非系统兜底)**:霞鹜文楷 LXGW(staticfile CDN)承 CJK 楷体、Noto Serif SC(Google)承拉丁衬线——与玄鉴同款。
- **主视觉**:竖排"双墨接笔"——原著墨在朱砂印「此後·墨筆續」处转花青(续写);背景幽灵水印「記/續/墨」。
- **动效**:GSAP + ScrollTrigger(CDN)——hero 载入时间线、滚动 reveal/错峰、水印/手稿视差、数字 count-up、卡片悬停抬升。
- **优雅降级**:GSAP/字体未加载(离线/严格 CSP,如 Claude Artifact)→ 1.2s 兜底全显、系统楷/宋 兜底、数字用内置真实值;`prefers-reduced-motion` 全尊重。
- **内容取自真实交付**:《天之炽》157→结局260、58.5 万字、104 章、21 agent、4 层记忆。

## 关于"为什么是手写 CSS 而不是 Vue/Tailwind/shadcn"
玄鉴落地页的样式本身也是**手写 `home.css`**(CSS 变量 + 自定义类),Vue 只是 SFC 外壳、Tailwind/reka-ui 基本没用在落地页——让它高级的是**网络字体 + 配色 + 巨字/水印构图**,已在此吸收。单页静态落地页用自包含 HTML/CSS 最省、最可移植(玄鉴最终也编译成静态 `dist-home` 部署)。若需与玄鉴同构的 Vue+Vite+Tailwind 工程版(便于并入其仓库/复用组件),可另起——按需再说。
