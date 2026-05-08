"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Layout, Menu, ConfigProvider, theme as antdTheme, Tooltip } from "antd";
import {
  ReadOutlined,
  ApartmentOutlined,
  QuestionCircleOutlined,
  BulbOutlined,
  CompassOutlined,
  EditOutlined,
  FileTextOutlined,
  DashboardOutlined,
  HomeOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  BgColorsOutlined,
  SunOutlined,
  MoonOutlined,
  GoldOutlined,
  TeamOutlined,
  ApiOutlined,
  SettingOutlined,
  BookOutlined,
} from "@ant-design/icons";
import { ThemeProvider, useTheme, type UiTheme } from "./ThemeProvider";

const { Sider } = Layout;

const NAV_ITEMS: { key: string; icon: React.ReactNode; label: string }[] = [
  { key: "/", icon: <HomeOutlined />, label: "首页" },
  { key: "/library", icon: <BookOutlined />, label: "书架" },
  { key: "/ingest", icon: <ReadOutlined />, label: "语料" },
  { key: "/graph", icon: <ApartmentOutlined />, label: "图谱" },
  { key: "/items", icon: <GoldOutlined />, label: "宝物功法" },
  { key: "/mysteries", icon: <QuestionCircleOutlined />, label: "疑点" },
  { key: "/predict", icon: <BulbOutlined />, label: "预测·章" },
  { key: "/arc", icon: <CompassOutlined />, label: "预测·全弧" },
  { key: "/sim", icon: <TeamOutlined />, label: "角色仿真" },
  { key: "/outline", icon: <EditOutlined />, label: "大纲" },
  { key: "/draft", icon: <FileTextOutlined />, label: "成稿" },
  { key: "/monitor", icon: <DashboardOutlined />, label: "监控" },
  { key: "/architecture", icon: <ApiOutlined />, label: "架构" },
  { key: "/settings", icon: <SettingOutlined />, label: "设置" },
];

export default function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider>
      <ShellInner>{children}</ShellInner>
    </ThemeProvider>
  );
}

function ShellInner({ children }: { children: React.ReactNode }) {
  const { theme, colorScheme } = useTheme();
  const isDark = colorScheme === "dark";
  return (
    <ConfigProvider
      theme={{
        algorithm: isDark ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
        token: {
          colorPrimary: isDark ? "#7aa2f7" : "#1565c0",
          colorBgContainer: isDark ? "#161922" : "#ffffff",
          colorBgElevated: isDark ? "#1f232f" : "#f0ede2",
          colorBorder: isDark ? "#2a2f3d" : "#d9d4c1",
        },
        components: {
          Menu: {
            darkItemBg: "transparent",
            darkSubMenuItemBg: "transparent",
            darkItemSelectedBg: isDark ? "rgba(122,162,247,0.15)" : "rgba(21,101,192,0.12)",
            darkItemHoverBg: isDark ? "rgba(255,255,255,0.04)" : "rgba(0,0,0,0.04)",
          },
        },
      }}
    >
      {theme === "modern" ? <ModernShell>{children}</ModernShell> : <ClassicShell>{children}</ClassicShell>}
    </ConfigProvider>
  );
}

// ---------------------------------------------------------------------------
// Modern: Antd Sider + brand title
// ---------------------------------------------------------------------------

function ModernShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() || "/";
  const [collapsed, setCollapsed] = useState(false);
  const [activeBook, setActiveBook] = useState<string | null>(null);
  const { setTheme, colorScheme, toggleColorScheme } = useTheme();

  useEffect(() => {
    fetch("http://localhost:8000/books")
      .then((r) => r.json())
      .then((d) => setActiveBook(d?.active || null))
      .catch(() => {});
  }, [pathname]);

  const selectedKey = (
    NAV_ITEMS
      .map((it) => it.key)
      .filter((k) => k !== "/" && pathname.startsWith(k))
      .sort((a, b) => b.length - a.length)[0]
  ) || "/";

  return (
    <Layout className="app-shell" hasSider>
      <Sider
        theme="dark"
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        collapsedWidth={64}
        width={200}
        trigger={null}
        style={{
          background: "var(--panel)",
          borderRight: "1px solid var(--border)",
          position: "sticky",
          top: 0,
          height: "100vh",
        }}
      >
        <Link href="/" style={{
          display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
          padding: collapsed ? "10px 4px" : "12px 8px",
          borderBottom: "1px solid var(--border)",
          gap: 4,
          textDecoration: "none",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <img
              src="/logo.png"
              alt="墨笔"
              width={collapsed ? 36 : 42}
              height={collapsed ? 36 : 42}
              style={{ display: "block" }}
            />
            {!collapsed && (
              <span className="brand-title" style={{ fontSize: 24, lineHeight: 1, color: "var(--accent-2)" }}>
                笔
              </span>
            )}
          </div>
          {!collapsed && activeBook && (
            <Tooltip title={`当前活跃书：${activeBook}`} placement="right">
              <Link href="/library" style={{
                fontSize: 11,
                color: "var(--accent-2)",
                textDecoration: "none",
                maxWidth: 170,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
                opacity: 0.85,
                marginTop: 2,
              }} onClick={(e) => e.stopPropagation()}>
                《{activeBook}》
              </Link>
            </Tooltip>
          )}
        </Link>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey]}
          items={NAV_ITEMS.map((it) => ({
            key: it.key,
            icon: it.icon,
            label: <Link href={it.key}>{it.label}</Link>,
          }))}
          style={{ background: "var(--panel)", borderRight: 0, marginTop: 8 }}
        />

        {/* Bottom controls */}
        <div style={{ position: "absolute", bottom: 12, left: 0, right: 0,
                       display: "flex", flexDirection: collapsed ? "column" : "row",
                       alignItems: "stretch",
                       justifyContent: "center", gap: 6, padding: "0 12px" }}>
          <Tooltip title={`切到${colorScheme === "dark" ? "亮色" : "暗色"}`} placement="right">
            <button onClick={toggleColorScheme} className="ghost"
              style={{ padding: "6px 10px", fontSize: 12, flex: collapsed ? "none" : 1 }}>
              {colorScheme === "dark" ? <SunOutlined /> : <MoonOutlined />}
              {!collapsed && (colorScheme === "dark" ? " 亮色" : " 暗色")}
            </button>
          </Tooltip>
          <Tooltip title="切到 classic 风格" placement="right">
            <button onClick={() => setTheme("classic")} className="ghost"
              style={{ padding: "6px 10px", fontSize: 12, flex: collapsed ? "none" : 1 }}>
              <BgColorsOutlined /> {!collapsed && "经典"}
            </button>
          </Tooltip>
          <Tooltip title={collapsed ? "展开" : "收起"} placement="right">
            <button onClick={() => setCollapsed(!collapsed)} className="ghost"
              style={{ padding: "6px 10px", fontSize: 12 }}>
              {collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            </button>
          </Tooltip>
        </div>
      </Sider>
      <Layout style={{ background: "var(--bg)" }}>
        <main className="app-content">{children}</main>
      </Layout>
    </Layout>
  );
}

// ---------------------------------------------------------------------------
// Classic: original top nav (no Sider, no Antd chrome)
// ---------------------------------------------------------------------------

function ClassicShell({ children }: { children: React.ReactNode }) {
  const { setTheme, colorScheme, toggleColorScheme } = useTheme();
  return (
    <>
      <nav className="topnav">
        <Link href="/" style={{ display: "flex", alignItems: "center", gap: 6, marginRight: 8 }}>
          <img src="/logo.png" alt="墨笔" width={28} height={28} style={{ display: "block" }} />
          <span className="brand-title" style={{ fontSize: 18, color: "var(--accent-2)", lineHeight: 1 }}>笔</span>
        </Link>
        <Link href="/">首页</Link>
        <Link href="/library">书架</Link>
        <Link href="/ingest">语料</Link>
        <Link href="/graph">图谱</Link>
        <Link href="/items">宝物功法</Link>
        <Link href="/mysteries">疑点</Link>
        <Link href="/predict">预测·章</Link>
        <Link href="/arc">预测·全弧</Link>
        <Link href="/sim">角色仿真</Link>
        <Link href="/outline">大纲</Link>
        <Link href="/draft">成稿</Link>
        <Link href="/monitor">监控</Link>
        <Link href="/architecture">架构</Link>
        <Link href="/settings">设置</Link>
        <button onClick={toggleColorScheme} className="ghost"
          style={{ marginLeft: "auto", padding: "4px 12px", fontSize: 12 }}>
          {colorScheme === "dark" ? <><SunOutlined /> 亮色</> : <><MoonOutlined /> 暗色</>}
        </button>
        <button onClick={() => setTheme("modern")} className="ghost"
          style={{ padding: "4px 12px", fontSize: 12 }}>
          <BgColorsOutlined /> 切到 modern
        </button>
      </nav>
      <main className="container">{children}</main>
    </>
  );
}
