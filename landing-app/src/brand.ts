// 墨笔品牌与文案单点。改中英文 / tagline / CTA 链接都改这里。
// 语义:墨 = 原著已落的墨;笔 = 续写之笔。核心命题「记忆 > 上下文」。
export const brand = {
  chinese: '墨笔',
  english: 'MoBi',
  englishSub: 'A memory-native engine for continuing long novels',
  tagline: '记忆驱动的长篇续写引擎',
  // 外链:已上线的续写作品阅读站
  readUrl: 'https://mobi-ai-novel.netlify.app/',
  // 背景装饰汉字(浮动,极低透明度)
  hanziFloat: ['記', '續', '墨'] as const,
  // 手稿签名印文(朱文竖排方章)
  sealText: ['此後', '墨筆續'] as const,
  twin: '孪生项目 · 墨析:跨书拆解 / 文风仿写',
} as const

// Proof 段:真实交付数字(《天之炽》157→260)
export interface Stat {
  value: number
  decimals?: number
  unit: string
  label: string
}
export const stats: Stat[] = [
  { value: 104, unit: '章', label: 'AI 续写(157→260)' },
  { value: 58.5, decimals: 1, unit: '万字', label: '续写篇幅' },
  { value: 21, unit: '个', label: '协作的 LLM agent' },
  { value: 4, unit: '层', label: '外部记忆栈' },
]
