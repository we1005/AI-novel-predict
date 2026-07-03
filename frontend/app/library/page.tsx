"use client";

import { useEffect, useState } from "react";
import { Modal, Tag, Tooltip, message, Empty, Spin, Input } from "antd";
import {
  BookOutlined,
  CheckCircleFilled,
  DeleteOutlined,
  ReloadOutlined,
  FolderOpenOutlined,
  ImportOutlined,
  FileTextOutlined,
  DatabaseOutlined,
} from "@ant-design/icons";
import { api } from "@/lib/api";
import PageTitle from "@/components/PageTitle";

type Book = {
  slug: string;
  title: string;
  active: boolean;
  has_corpus: boolean;
  has_db: boolean;
  corpus_bytes: number;
  db_bytes: number;
  is_branch?: boolean;
  parent_slug?: string | null;
  branch_name?: string | null;
  outline_run_id?: number | null;
  base_chapter?: number | null;
  is_compose?: boolean;   // 墨析 compose 虚拟书 → 墨笔书架隐藏
};

type LibraryFile = {
  filename: string;
  stem: string;
  size: number;
  suggested_slug: string;
  already_imported: boolean;
};

type Bundle = {
  active: string | null;
  books: Book[];
  library_dir: string;
  library_files: LibraryFile[];
};

function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

export default function LibraryPage() {
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState<string | null>(null);
  const [importTitle, setImportTitle] = useState<Record<string, string>>({});
  const [forkParent, setForkParent] = useState<string | null>(null);
  const [forkName, setForkName] = useState("");

  const doFork = async () => {
    if (!forkParent || !forkName.trim()) return;
    const parent = forkParent;
    setForkParent(null);
    setWorking(parent);
    try {
      const r = await api.booksFork(parent, forkName.trim(), { setActive: true });
      message.success(`已建分支「${r.branch_name}」并切换过去(克隆 ${r.base_chapter} 章基线)`);
      setForkName("");
      await refresh();
      setTimeout(() => window.location.reload(), 700);
    } catch (e) {
      message.error("建分支失败：" + String(e));
    } finally {
      setWorking(null);
    }
  };

  const refresh = async () => {
    setLoading(true);
    try {
      setBundle(await api.booksList());
    } catch (e) {
      message.error("加载失败：" + String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { refresh(); }, []);

  const switchTo = async (slug: string) => {
    if (bundle?.active === slug) return;
    setWorking(slug);
    try {
      await api.booksSetActive(slug);
      message.success(`已切换到「${slug}」`);
      await refresh();
      // Force a hard refresh of any open page that caches data — the simplest
      // signal is just to reload the whole app.
      setTimeout(() => window.location.reload(), 600);
    } catch (e) {
      message.error("切换失败：" + String(e));
    } finally {
      setWorking(null);
    }
  };

  const remove = (slug: string) => {
    Modal.confirm({
      title: `删除《${slug}》？`,
      content: "这会永久删除该书的 SQLite 数据库 + ChromaDB + 语料文件。原始 .txt 不受影响。",
      okText: "删除",
      okButtonProps: { danger: true },
      onOk: async () => {
        setWorking(slug);
        try {
          await api.booksDelete(slug);
          message.success("已删除");
          await refresh();
        } catch (e) {
          message.error("删除失败：" + String(e));
        } finally {
          setWorking(null);
        }
      },
    });
  };

  const importFile = async (filename: string) => {
    setWorking(filename);
    try {
      const title = importTitle[filename] || undefined;
      const r = await api.booksImport(filename, title, true);
      message.success(`已导入「${r.slug}」并切换为活跃书`);
      await refresh();
      setTimeout(() => window.location.reload(), 800);
    } catch (e) {
      message.error("导入失败：" + String(e));
    } finally {
      setWorking(null);
    }
  };

  if (loading || !bundle) {
    return (
      <div className="container">
        <PageTitle title="书架" />
        <div className="card"><Spin /> 加载中…</div>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 1240 }}>
      <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
        <PageTitle
          title="书架"
          subtitle="多书切换 · 每本书独立 SQLite + ChromaDB + 语料 · 模型设置全局共享"
        />
        <button className="ghost" onClick={refresh} style={{ padding: "6px 14px" }}>
          <ReloadOutlined /> 刷新
        </button>
      </div>

      <p className="muted" style={{ fontSize: 12, marginTop: 6, marginBottom: 16, lineHeight: 1.7,
        background: "var(--panel-2)", padding: "8px 12px", borderRadius: 8, borderLeft: "3px solid var(--accent)" }}>
        🌿 <b>分支</b> = 某条「整本故事弧候选」的独立续写线,记忆与原著/其它分支<b>隔离</b>。
        想<b>在分支里续写 / 推演 / 回滚</b> → 点该分支的 <b style={{ color: "var(--accent-2)" }}>「切换到本书」</b>(把它设为当前工作书);
        图谱 / 宝物 / 疑点页顶部的「视角」下拉<b>只是只读预览、不能在上面写</b>。
      </p>

      {/* 已导入书 */}
      <div className="card" style={{ marginBottom: 20 }}>
        <h3 style={{ marginTop: 0, display: "flex", alignItems: "center", gap: 8 }}>
          <BookOutlined /> 已导入
          <span className="muted" style={{ fontSize: 12, fontWeight: "normal" }}>
            {bundle.books.filter((b) => !b.is_compose).length} 本
          </span>
        </h3>

        {bundle.books.length === 0 && (
          <Empty description="还没有导入任何书。先到下方「文件夹扫描」导入一本。" />
        )}

        <div style={{
          display: "grid",
          gap: 14,
          gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))",
          alignItems: "start",   // 不拉伸,带分支的书更高时其它书不跟着变高
        }}>
          {bundle.books.filter((b) => !b.is_branch && !b.is_compose).map((p) => {
            const branches = bundle.books.filter((b) => b.is_branch && !b.is_compose && b.parent_slug === p.slug);
            return (
              <div key={p.slug} style={{ display: "flex", flexDirection: "column" }}>
                <BookCard
                  book={p}
                  busy={working === p.slug}
                  onSwitch={() => switchTo(p.slug)}
                  onDelete={() => remove(p.slug)}
                  onFork={() => { setForkParent(p.slug); setForkName(""); }}
                />
                {branches.length > 0 && (
                  <div style={{ marginTop: 8, marginLeft: 12, paddingLeft: 12,
                    borderLeft: "2px solid var(--border)", display: "flex", flexDirection: "column", gap: 6 }}>
                    {branches.map((br) => (
                      <BranchRow
                        key={br.slug}
                        book={br}
                        busy={working === br.slug}
                        onSwitch={() => switchTo(br.slug)}
                        onDelete={() => remove(br.slug)}
                      />
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      <Modal
        title={`从《${forkParent || ""}》建大纲分支`}
        open={!!forkParent}
        onOk={doFork}
        onCancel={() => setForkParent(null)}
        okText="建分支"
        okButtonProps={{ disabled: !forkName.trim() }}
      >
        <p className="muted" style={{ fontSize: 13, marginTop: 0 }}>
          分支会克隆本书的原著记忆(实体/伏笔/关系)作基线,得到一本独立的派生书;
          之后在这条分支里的续写与回灌只写进它自己的库,与原著/其它分支<b>互不污染</b>,可单独回滚。
        </p>
        <Input
          autoFocus
          placeholder="分支名,如「稳健向」「爽文向」「大纲A」"
          value={forkName}
          onChange={(e) => setForkName(e.target.value)}
          onPressEnter={doFork}
        />
      </Modal>

      {/* 文件夹扫描 */}
      <div className="card">
        <h3 style={{ marginTop: 0, display: "flex", alignItems: "center", gap: 8 }}>
          <FolderOpenOutlined /> 库文件夹
        </h3>
        <p className="muted" style={{ marginTop: -4, fontSize: 12 }}>
          把小说 <code style={{ fontSize: 11 }}>.txt</code> 放进 <code style={{ fontSize: 11, background: "var(--bg)", padding: "2px 6px", borderRadius: 4 }}>{bundle.library_dir}</code> ，刷新即可导入。支持 GBK/UTF-8/Big5 自动识别。
        </p>

        {bundle.library_files.length === 0 ? (
          <div style={{ padding: 24, textAlign: "center", color: "var(--muted)", fontSize: 13 }}>
            该文件夹为空。把 .txt 拖进去后点上面「刷新」。
          </div>
        ) : (
          <div style={{
            display: "grid",
            gap: 10,
            gridTemplateColumns: "repeat(auto-fill, minmax(360px, 1fr))",
            marginTop: 14,
          }}>
            {bundle.library_files.map((f) => (
              <LibraryFileCard
                key={f.filename}
                file={f}
                title={importTitle[f.filename] || ""}
                onTitleChange={(v) => setImportTitle({ ...importTitle, [f.filename]: v })}
                onImport={() => importFile(f.filename)}
                busy={working === f.filename}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------

function BookCard({
  book, busy, onSwitch, onDelete, onFork,
}: {
  book: Book;
  busy: boolean;
  onSwitch: () => void;
  onDelete: () => void;
  onFork?: () => void;
}) {
  return (
    <div style={{
      border: book.active ? "2px solid var(--accent)" : "1px solid var(--border)",
      borderRadius: 12,
      padding: 16,
      background: book.active ? "rgba(122,162,247,0.08)" : "var(--bg)",
      transition: "all 0.15s",
      position: "relative",
    }}>
      {book.active && (
        <CheckCircleFilled style={{
          position: "absolute", top: 12, right: 12,
          color: "var(--accent)", fontSize: 18,
        }} />
      )}

      <div style={{
        fontFamily: "var(--decorative)",
        fontSize: 22,
        color: book.active ? "var(--accent-2)" : "var(--text)",
        letterSpacing: 2,
        marginBottom: 4,
      }}>
        {book.title}
      </div>
      <code style={{ fontSize: 11, color: "var(--muted)" }}>{book.slug}</code>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 12 }}>
        {book.has_corpus && (
          <Tag color="green" style={{ fontSize: 11, margin: 0 }}>
            <FileTextOutlined /> {fmtBytes(book.corpus_bytes)}
          </Tag>
        )}
        {book.has_db && (
          <Tag color="blue" style={{ fontSize: 11, margin: 0 }}>
            <DatabaseOutlined /> {fmtBytes(book.db_bytes)}
          </Tag>
        )}
        {!book.has_corpus && (
          <Tag color="warning" style={{ fontSize: 11, margin: 0 }}>无语料</Tag>
        )}
        {book.active && <Tag color="purple" style={{ fontSize: 11, margin: 0 }}>当前</Tag>}
        {book.is_branch && (
          <Tag color="geekblue" style={{ fontSize: 11, margin: 0 }}>
            🌿 分支 · 基线{book.base_chapter ?? "?"}章
          </Tag>
        )}
      </div>

      <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
        <button
          onClick={onSwitch}
          disabled={book.active || busy}
          style={{
            flex: 1,
            padding: "6px 12px",
            fontSize: 12,
            background: book.active ? "var(--panel-2)" : "var(--accent)",
            opacity: book.active ? 0.5 : 1,
          }}
        >
          {book.active ? "已激活" : busy ? "切换中…" : "切换到本书"}
        </button>
        {onFork && (
          <Tooltip title="建一条大纲分支(克隆本书作独立派生书,续写互不污染、可单独回滚)">
            <button
              className="ghost"
              onClick={onFork}
              disabled={busy}
              style={{ padding: "6px 12px", fontSize: 12 }}
            >
              🌿 建分支
            </button>
          </Tooltip>
        )}
        <Tooltip title={book.active ? "先切到别的书才能删" : "永久删除"}>
          <button
            className="ghost"
            onClick={onDelete}
            disabled={book.active || busy}
            style={{ padding: "6px 12px", fontSize: 12 }}
          >
            <DeleteOutlined />
          </button>
        </Tooltip>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// 分支折叠成紧凑单行(挂在原著卡片下),避免每个分支占一整张大卡。

function BranchRow({
  book, busy, onSwitch, onDelete,
}: {
  book: Book;
  busy: boolean;
  onSwitch: () => void;
  onDelete: () => void;
}) {
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 8,
      padding: "6px 10px", borderRadius: 8, fontSize: 12,
      border: book.active ? "1px solid var(--accent)" : "1px solid var(--border)",
      background: book.active ? "rgba(122,162,247,0.08)" : "var(--bg)",
    }}>
      <span>🌿</span>
      <span
        title={book.slug}
        style={{ fontWeight: 600, flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
      >
        {book.branch_name || book.title}
      </span>
      {book.base_chapter != null && (
        <span className="muted" style={{ fontSize: 10, whiteSpace: "nowrap" }}>基线{book.base_chapter}章</span>
      )}
      {book.active ? (
        <span style={{ fontSize: 11, color: "var(--accent)", whiteSpace: "nowrap" }}>当前</span>
      ) : (
        <button onClick={onSwitch} disabled={busy} style={{ fontSize: 11, padding: "3px 12px" }}>
          {busy ? "…" : "切换"}
        </button>
      )}
      <Tooltip title={book.active ? "先切到别的书才能删" : "删除此分支"}>
        <button className="ghost" onClick={onDelete} disabled={book.active || busy}
          style={{ fontSize: 11, padding: "3px 7px" }}>
          <DeleteOutlined />
        </button>
      </Tooltip>
    </div>
  );
}

// ---------------------------------------------------------------------------

function LibraryFileCard({
  file, title, onTitleChange, onImport, busy,
}: {
  file: LibraryFile;
  title: string;
  onTitleChange: (v: string) => void;
  onImport: () => void;
  busy: boolean;
}) {
  const dimmed = file.already_imported;
  return (
    <div style={{
      border: "1px dashed var(--border)",
      borderRadius: 10,
      padding: 12,
      background: "var(--bg)",
      opacity: dimmed ? 0.55 : 1,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
        <FileTextOutlined style={{ color: "var(--muted)" }} />
        <code style={{ fontSize: 12, fontWeight: 600 }}>{file.filename}</code>
        <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--muted)" }}>
          {fmtBytes(file.size)}
        </span>
      </div>

      {dimmed ? (
        <div className="muted" style={{ fontSize: 11 }}>
          已存在《{file.suggested_slug}》——重命名 .txt 后再扫描即可作为新书导入
        </div>
      ) : (
        <>
          <div style={{ display: "flex", gap: 6, marginBottom: 6, alignItems: "center" }}>
            <Input
              size="small"
              placeholder={`书名（默认: ${file.suggested_slug}）`}
              value={title}
              onChange={(e) => onTitleChange(e.target.value)}
              style={{ fontSize: 12 }}
            />
          </div>
          <button
            onClick={onImport}
            disabled={busy}
            style={{ width: "100%", padding: "6px 12px", fontSize: 12 }}
          >
            <ImportOutlined /> {busy ? "导入中…" : "导入并切换"}
          </button>
          <div className="muted" style={{ fontSize: 10, marginTop: 6 }}>
            导入只复制语料；之后到 <a href="/ingest" style={{ color: "var(--accent)" }}>语料</a> 跑分章 + 抽取
          </div>
        </>
      )}
    </div>
  );
}
