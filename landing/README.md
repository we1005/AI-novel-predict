# 墨笔 · 产品介绍页(landing)

可托管的**单文件**介绍页,对外讲清"墨笔靠先建结构化记忆(读者的大脑)续写百万字长篇"。风格:**暗墨 × 毛玻璃 × Apple 动效**。

- **打开**:`open landing/index.html`(或丢到 Netlify / GitHub Pages 等静态托管)。
- **主视觉**:竖排"双墨接笔"——原著白墨在朱砂印「此後·墨筆續」处转花青(续写),载入时花青渗入、印章弹落。
- **双墨编码**:白墨=原著 · 花青=AI 续写 · 朱砂=接笔之缝(颜色即信息)。
- **动效**:GSAP + ScrollTrigger(CDN)——hero 载入时间线、滚动 reveal/错峰、手稿视差、数字 count-up、玻璃卡悬停。背景墨色 aurora 与颗粒纯 CSS。
- **优雅降级**:GSAP 未加载(离线 / 严格 CSP,如 Claude Artifact)时 1.2s 兜底显示全部内容,数字用内置真实值,aurora 仍靠 CSS 动;`prefers-reduced-motion` 全尊重。
- **字体**:系统中文栈(楷体标题 / 宋体正文 / 等宽数据),无外链字体。
- **内容取自真实交付**:《天之炽》157→结局260、58.5 万字、104 章、21 agent、4 层记忆;CTA 直达在线 demo。

由 frontend-design / artifact-design / gsap-scrolltrigger 技能产出;可分享版同步为 Claude Artifact。
