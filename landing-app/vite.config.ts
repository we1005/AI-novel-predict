import path from 'node:path'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'

// 墨笔落地页:独立静态站。构建产物 dist/,可直接 netlify deploy --dir=dist。
// base: './' → 资源全走相对路径,产物可放任意子路径 / 直接 file:// 打开都不断链
// (本项目会把 dist 同步进 ../结果/,阅读站作为 结果/read/ 子目录相对链接)。
export default defineConfig({
  base: './',
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
