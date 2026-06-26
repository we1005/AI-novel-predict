"use client";
// 轻量线性图标(stroke=currentColor,无需第三方依赖)
const P: Record<string, string> = {
  speedread: "M4 5h16M4 12h16M4 19h10",                                   // 速读=行
  pacing: "M3 12h3l3 8 4-16 3 8h5",                                       // 节拍=脉搏
  style: "M12 19l7-7 3 3-7 7-3-3zM18 13l-1.5-7.5L2 2l3.5 14.5L13 18z",    // 文笔=笔
  worldview: "M12 3a9 9 0 100 18 9 9 0 000-18zM3 12h18M12 3c2.5 3 2.5 15 0 18M12 3c-2.5 3-2.5 15 0 18", // 世界=球
  relationship: "M9 11a3 3 0 100-6 3 3 0 000 6zM17 11a3 3 0 100-6M3 20a6 6 0 0112 0M15 14a6 6 0 016 6", // 关系=人
  settings: "M12 2l8 4v6c0 5-3.5 8-8 10-4.5-2-8-5-8-10V6z",               // 设定=盾
  pov: "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM12 15a3 3 0 100-6 3 3 0 000 6z", // 视角=眼
  golden: "M3 17l6-6 4 4 8-8M21 7h-5M21 7v5",                            // 金手指=上升
  analyze: "M4 4h7v7H4zM13 4h7v4h-7zM13 11h7v9h-7zM4 13h7v7H4z",          // 深度分析=网格
  compose: "M12 19l7-7 3 3-7 7-3-3zM5 6l1 4 4 1-4 1-1 4-1-4-4-1 4-1z",   // 仿写=魔法笔
};

export default function Icon({ k, size = 18 }: { k: string; size?: number }) {
  const d = P[k];
  if (!d) return null;
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <path d={d} />
    </svg>
  );
}
