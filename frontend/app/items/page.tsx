"use client";

import { useEffect, useMemo, useState } from "react";
import { Drawer, Tag, Tooltip } from "antd";
import {
  GoldOutlined,
  ThunderboltOutlined,
  QuestionCircleOutlined,
} from "@ant-design/icons";
import { api } from "@/lib/api";
import PageTitle from "@/components/PageTitle";

type Event = { chapter: number; chapter_title?: string; kind: "gained" | "lost" | "used"; note?: string };
type RelatedFs = {
  id: number; type: string; status: string;
  planted_chapter: number; resolved_chapter: number | null;
  description: string; resolved_description?: string | null;
};
type Item = {
  name: string;
  kind: "item" | "skill" | "concept";
  first_seen_chapter: number;
  last_seen_chapter: number;
  still_owned: boolean;
  entity_id: number | null;
  entity_importance?: number | null;
  description: string;
  events: Event[];
  related_foreshadows: RelatedFs[];
};

const KIND_COLOR: Record<string, string> = {
  item: "var(--c-foreshadow)",  // 金色
  skill: "var(--c-character)",  // 绿色
  concept: "var(--c-mystery)",
};
const KIND_LABEL: Record<string, string> = {
  item: "宝物",
  skill: "功法",
  concept: "概念",
};
const KIND_ICON: Record<string, React.ReactNode> = {
  item: <GoldOutlined />,
  skill: <ThunderboltOutlined />,
  concept: <QuestionCircleOutlined />,
};

const EVENT_COLOR: Record<string, string> = {
  gained: "var(--good)",
  lost: "var(--bad)",
  used: "var(--accent)",
};
const EVENT_LABEL: Record<string, string> = {
  gained: "获得",
  lost: "失去",
  used: "运用",
};

export default function ItemsPage() {
  const [data, setData] = useState<{ hero: any; items: Item[]; catalog_mode?: boolean } | null>(null);
  const [filterKind, setFilterKind] = useState<"all" | "item" | "skill" | "concept">("all");
  const [filterStatus, setFilterStatus] = useState<"all" | "owned" | "lost">("all");
  const [filterFs, setFilterFs] = useState<"all" | "with_fs">("all");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Item | null>(null);

  useEffect(() => {
    api.heroItems().then(setData).catch(() => setData({ hero: null, items: [] }));
  }, []);

  const stats = useMemo(() => {
    if (!data) return { items: 0, skills: 0, concepts: 0, owned: 0, withFs: 0, total: 0 };
    const items = data.items;
    return {
      items: items.filter((x) => x.kind === "item").length,
      skills: items.filter((x) => x.kind === "skill").length,
      concepts: items.filter((x) => x.kind === "concept").length,
      owned: items.filter((x) => x.still_owned).length,
      withFs: items.filter((x) => x.related_foreshadows.length > 0).length,
      total: items.length,
    };
  }, [data]);

  const filtered = useMemo(() => {
    if (!data) return [];
    const q = search.trim().toLowerCase();
    return data.items.filter((it) => {
      if (filterKind !== "all" && it.kind !== filterKind) return false;
      if (filterStatus === "owned" && !it.still_owned) return false;
      if (filterStatus === "lost" && it.still_owned) return false;
      if (filterFs === "with_fs" && it.related_foreshadows.length === 0) return false;
      if (q && !(
        it.name.toLowerCase().includes(q) ||
        it.description.toLowerCase().includes(q)
      )) return false;
      return true;
    });
  }, [data, filterKind, filterStatus, filterFs, search]);

  return (
    <>
      <PageTitle title="宝物功法谱"
        subtitle={data?.catalog_mode
          ? "全书宝物 / 功法目录（按重要度与伏笔关联排序）— 物中藏笔，看哪些钩子还没收"
          : `${data?.hero?.name || "主角"}沿途获得 / 失去的物品与功法 — 物中藏笔，看哪些钩子还没收`} />

      {data?.catalog_mode && (
        <div style={{ margin: "0 0 14px", padding: "8px 12px", borderRadius: 6, fontSize: 12,
                      background: "rgba(82,196,26,0.1)", border: "1px solid var(--good)", color: "var(--good)" }}>
          ⓘ 本书未按"主角库存"记录物品（如机甲/多主角设定），已自动切换为「全书宝物目录」模式，按重要度+伏笔关联展示 {data.items.length} 件。
        </div>
      )}

      {data?.hero?.id && !data?.catalog_mode && (
        <div style={{ marginBottom: 14 }}>
          <a
            href={`/character/${data.hero.id}`}
            style={{
              display: "inline-block",
              padding: "6px 14px",
              background: "var(--accent)",
              color: "#fff",
              borderRadius: 6,
              fontSize: 13,
              textDecoration: "none",
            }}
          >
            找 {data.hero.name} 对话 →
          </a>
        </div>
      )}

      <div className="row" style={{ justifyContent: "flex-start", marginBottom: 18 }}>
        <Stat k="总数" v={stats.total} />
        <Stat k="宝物" v={stats.items} color="var(--c-foreshadow)" />
        <Stat k="功法" v={stats.skills} color="var(--c-character)" />
        <Stat k="还在身上" v={stats.owned} color="var(--good)" />
        <Stat k="含伏笔" v={stats.withFs} color="var(--c-mystery)" />
      </div>

      <div className="card">
        <div className="row" style={{ alignItems: "center", flexWrap: "wrap" }}>
          <span className="muted">类型</span>
          {(["all", "item", "skill", "concept"] as const).map((k) => (
            <button key={k} onClick={() => setFilterKind(k)}
              className={filterKind === k ? "" : "ghost"}
              style={{ padding: "4px 10px", fontSize: 12 }}>
              {k === "all" ? "全部" : KIND_LABEL[k]}
            </button>
          ))}
          <span className="muted" style={{ marginLeft: 14 }}>状态</span>
          {(["all", "owned", "lost"] as const).map((s) => (
            <button key={s} onClick={() => setFilterStatus(s)}
              className={filterStatus === s ? "" : "ghost"}
              style={{ padding: "4px 10px", fontSize: 12 }}>
              {s === "all" ? "全部" : s === "owned" ? "还在" : "已失去"}
            </button>
          ))}
          <span className="muted" style={{ marginLeft: 14 }}>伏笔</span>
          {(["all", "with_fs"] as const).map((f) => (
            <button key={f} onClick={() => setFilterFs(f)}
              className={filterFs === f ? "" : "ghost"}
              style={{ padding: "4px 10px", fontSize: 12 }}>
              {f === "all" ? "全部" : "仅含伏笔"}
            </button>
          ))}
          <input
            placeholder="搜索名称 / 描述…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ flex: 1, minWidth: 200, marginLeft: 14 }}
          />
        </div>
      </div>

      <div style={{
        display: "grid", gap: 12,
        gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
      }}>
        {filtered.map((it) => (
          <ItemCard key={it.name} item={it} onClick={() => setSelected(it)} />
        ))}
        {filtered.length === 0 && data && (
          <div className="card muted" style={{ gridColumn: "1 / -1" }}>没有匹配的物品</div>
        )}
        {!data && <div className="card muted">加载中…</div>}
      </div>

      <Drawer
        title={selected ? `${KIND_LABEL[selected.kind]} · ${selected.name}` : ""}
        placement="right"
        width={560}
        open={!!selected}
        onClose={() => setSelected(null)}
        mask={false}
      >
        {selected && <ItemDetail item={selected} />}
      </Drawer>
    </>
  );
}

function Stat({ k, v, color }: { k: string; v: any; color?: string }) {
  return (
    <div className="metric" style={{ minWidth: 110, padding: "10px 16px" }}>
      <div className="k" style={color ? { color } : undefined}>{k}</div>
      <div className="v" style={{ fontFamily: "var(--serif)", fontSize: 22 }}>{v}</div>
    </div>
  );
}

function ItemCard({ item, onClick }: { item: Item; onClick: () => void }) {
  const color = KIND_COLOR[item.kind] || "var(--muted)";
  const span = item.last_seen_chapter - item.first_seen_chapter;
  return (
    <div onClick={onClick} className="card" style={{
      marginBottom: 0,
      borderTop: `3px solid ${color}`,
      cursor: "pointer",
      opacity: item.still_owned ? 1 : 0.65,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
        <span style={{ color, fontSize: 14 }}>{KIND_ICON[item.kind]}</span>
        <span className="tag" style={{ background: `${color}25`, color, fontWeight: 600 }}>
          {KIND_LABEL[item.kind]}
        </span>
        {!item.still_owned && (
          <span className="tag" style={{ background: "rgba(247,118,142,.15)", color: "var(--bad)" }}>已失去</span>
        )}
        {item.related_foreshadows.length > 0 && (
          <span className="tag" style={{
            marginLeft: "auto",
            background: "rgba(187,154,247,.18)", color: "var(--c-mystery)",
            fontWeight: 600,
          }}>
            含 {item.related_foreshadows.length} 伏笔
          </span>
        )}
      </div>

      <div className="prose-cn" style={{
        fontSize: 16, fontWeight: 600, color: "var(--text)", marginBottom: 4,
        whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
      }}>
        {item.name}
      </div>

      <div className="muted" style={{ fontSize: 12, marginBottom: 6 }}>
        第 {item.first_seen_chapter} 章
        {span > 0 && ` → 第 ${item.last_seen_chapter} 章`}
        {" · "}{item.events.length} 次事件
      </div>

      {item.description && (
        <div style={{
          fontSize: 12, lineHeight: 1.55, color: "var(--muted)",
          display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: "vertical",
          overflow: "hidden",
        }}>
          {item.description}
        </div>
      )}

      {/* tiny event row */}
      {item.events.length > 1 && (
        <div style={{ display: "flex", gap: 3, marginTop: 8 }}>
          {item.events.slice(0, 12).map((e, i) => (
            <Tooltip key={i} title={`第${e.chapter}章 ${EVENT_LABEL[e.kind]}`}>
              <span style={{
                width: 8, height: 8, borderRadius: "50%",
                background: EVENT_COLOR[e.kind] || "var(--muted)",
              }} />
            </Tooltip>
          ))}
          {item.events.length > 12 && <span className="muted" style={{ fontSize: 10 }}>+{item.events.length - 12}</span>}
        </div>
      )}
    </div>
  );
}

function ItemDetail({ item }: { item: Item }) {
  const color = KIND_COLOR[item.kind] || "var(--muted)";
  return (
    <div className="prose-cn">
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 12 }}>
        <Tag color={color}>{KIND_LABEL[item.kind]}</Tag>
        <Tag>第 {item.first_seen_chapter} 章首现</Tag>
        {item.still_owned ? (
          <Tag color="green">还在身上</Tag>
        ) : (
          <Tag color="red">第 {item.last_seen_chapter} 章失去</Tag>
        )}
        {item.related_foreshadows.length > 0 && (
          <Tag color="purple">关联 {item.related_foreshadows.length} 条伏笔</Tag>
        )}
      </div>

      {item.description && (
        <div style={{
          background: "var(--panel-2)", padding: 12, borderRadius: 6,
          borderLeft: `3px solid ${color}`,
          marginBottom: 16,
        }}>
          <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 4, fontWeight: 600 }}>描述</div>
          <p style={{ margin: 0, fontSize: 13, lineHeight: 1.7 }}>{item.description}</p>
        </div>
      )}

      <div style={{ marginBottom: 16 }}>
        <h3 style={{ fontSize: 14, color: "var(--text)", borderLeft: `3px solid ${color}`, paddingLeft: 8, marginBottom: 8 }}>
          演变时间线（{item.events.length}）
        </h3>
        <div style={{ position: "relative", paddingLeft: 14 }}>
          <div style={{ position: "absolute", left: 4, top: 6, bottom: 6, width: 2, background: "var(--border)" }} />
          {item.events.map((e, i) => (
            <div key={i} style={{ position: "relative", padding: "8px 0 8px 16px" }}>
              <div style={{
                position: "absolute", left: -3, top: 12, width: 10, height: 10,
                borderRadius: "50%", background: EVENT_COLOR[e.kind] || "var(--muted)",
                boxShadow: "0 0 0 2px var(--panel)",
              }} />
              <div style={{ fontSize: 12, color: "var(--muted)" }}>
                <span style={{ color: EVENT_COLOR[e.kind] || "var(--muted)", fontWeight: 600 }}>
                  {EVENT_LABEL[e.kind]}
                </span>
                {" · "}第 {e.chapter} 章 {e.chapter_title}
              </div>
              {e.note && <div style={{ fontSize: 13, marginTop: 2 }}>{e.note}</div>}
            </div>
          ))}
        </div>
      </div>

      {item.related_foreshadows.length > 0 && (
        <div>
          <h3 style={{ fontSize: 14, color: "var(--text)", borderLeft: "3px solid var(--c-mystery)", paddingLeft: 8, marginBottom: 8 }}>
            物中之笔 — 关联伏笔
          </h3>
          <div style={{ display: "grid", gap: 8 }}>
            {item.related_foreshadows.map((f) => (
              <div key={f.id} style={{
                background: "var(--panel-2)", padding: 10, borderRadius: 6,
                borderLeft: `3px solid ${f.status === "open" ? "var(--c-foreshadow)" : "var(--good)"}`,
              }}>
                <div style={{ display: "flex", gap: 4, alignItems: "center", marginBottom: 4 }}>
                  <Tag color="purple" style={{ margin: 0, fontSize: 11 }}>{f.type}</Tag>
                  <Tag color={f.status === "open" ? "gold" : "green"} style={{ margin: 0, fontSize: 11 }}>
                    {f.status === "open" ? "未收束" : "已收束"}
                  </Tag>
                  <span className="muted" style={{ fontSize: 11 }}>
                    第 {f.planted_chapter} 章
                    {f.resolved_chapter && ` → 第 ${f.resolved_chapter} 章`}
                  </span>
                </div>
                <div style={{ fontSize: 13, lineHeight: 1.6 }}>{f.description}</div>
                {f.resolved_description && (
                  <div style={{ fontSize: 12, color: "var(--good)", marginTop: 4 }}>
                    → {f.resolved_description}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
