"use client";
import dynamic from "next/dynamic";
const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

// 统一注入深色底/浅色字,免依赖 echarts 内置 dark 主题注册。
export function dark(option: any) {
  return {
    backgroundColor: "transparent",
    textStyle: { color: "#574f40", fontFamily: "ui-monospace, 'SF Mono', Menlo, monospace" },
    tooltip: {
      backgroundColor: "#fbfaf4", borderColor: "#d6d0bf",
      textStyle: { color: "#211d16", fontFamily: "-apple-system, 'PingFang SC', sans-serif" },
      ...(option.tooltip || {}),
    },
    ...option,
  };
}

export default function Chart({ option, height = 320 }: { option: any; height?: number }) {
  return (
    <ReactECharts
      option={dark(option)}
      style={{ height, width: "100%" }}
      opts={{ renderer: "canvas" }}
      notMerge
    />
  );
}
