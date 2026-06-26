/** @type {import('next').NextConfig} */
const BACKEND = process.env.NAIMITATE_BACKEND || "http://localhost:8100";
module.exports = {
  reactStrictMode: true,
  async rewrites() {
    // 前端同源调 /api/* → 转发到 naimitate 后端,免 CORS / 配置麻烦
    return [{ source: "/api/:path*", destination: `${BACKEND}/:path*` }];
  },
};
