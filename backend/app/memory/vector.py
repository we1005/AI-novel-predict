"""Chroma embedding store for chapter-level semantic recall.

Uses ``BAAI/bge-large-zh-v1.5`` via sentence-transformers (loaded lazily — heavy).
Index built from the splitter's UTF-8 corpus, one document per chapter (further
chunked into ~800-char paragraphs for finer recall).
"""

from __future__ import annotations

from functools import lru_cache

from ..config import EMBEDDING_MODEL

_COLLECTION = "chapters_zh"

# Chroma client cache, keyed by chroma directory path so switching active book
# rebuilds against the new persistent dir.
_clients: dict[str, object] = {}


def _client():
    from ..books.library import active_paths
    chroma_dir = active_paths()["chroma_dir"]
    chroma_dir.mkdir(parents=True, exist_ok=True)
    key = str(chroma_dir)
    cached = _clients.get(key)
    if cached is not None:
        return cached
    import chromadb
    from chromadb.config import Settings
    cli = chromadb.PersistentClient(path=key, settings=Settings(anonymized_telemetry=False))
    _clients[key] = cli
    return cli


@lru_cache(maxsize=1)
def _embedder():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(EMBEDDING_MODEL)


def _embed(texts: list[str]) -> list[list[float]]:
    return _embedder().encode(texts, normalize_embeddings=True).tolist()


def _get_or_create():
    return _client().get_or_create_collection(_COLLECTION, metadata={"hnsw:space": "cosine"})


def _chunk(text_body: str, target: int = 800) -> list[str]:
    out: list[str] = []
    paragraphs = [p.strip() for p in text_body.split("\n") if p.strip()]
    buf = ""
    for p in paragraphs:
        if len(buf) + len(p) + 1 > target and buf:
            out.append(buf)
            buf = p
        else:
            buf = (buf + "\n" + p) if buf else p
    if buf:
        out.append(buf)
    return out


def index_chapters(chapters: list[tuple[int, str, int, int]], corpus: str) -> int:
    coll = _get_or_create()
    ids: list[str] = []
    docs: list[str] = []
    metas: list[dict] = []
    for num, title, start, end in chapters:
        body = corpus[start:end]
        for i, ch in enumerate(_chunk(body)):
            ids.append(f"{num}-{i}")
            docs.append(ch)
            metas.append({"chapter": num, "title": title, "chunk": i})
    if not ids:
        return 0
    embs = _embed(docs)
    # Upsert in batches of 256 to bound memory.
    for i in range(0, len(ids), 256):
        coll.upsert(
            ids=ids[i : i + 256],
            documents=docs[i : i + 256],
            metadatas=metas[i : i + 256],
            embeddings=embs[i : i + 256],
        )
    return len(ids)


def query(text: str, k: int = 8, before_chapter: int | None = None) -> list[dict]:
    coll = _get_or_create()
    where = {"chapter": {"$lt": before_chapter}} if before_chapter is not None else None
    res = coll.query(
        query_embeddings=_embed([text]),
        n_results=k,
        where=where,
    )
    out: list[dict] = []
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]
    for i, doc in enumerate(docs):
        meta = metas[i] if i < len(metas) else {}
        out.append({
            "chapter": meta.get("chapter"),
            "title": meta.get("title"),
            "chunk": meta.get("chunk"),
            "text": doc,
            "distance": dists[i] if i < len(dists) else None,
        })
    return out


# ---------------------------------------------------------------------------
# E2:启用支撑——依赖探测 / 模型加载状态 / 索引计数 / 重建索引(均带守卫)
# ---------------------------------------------------------------------------

def deps_available() -> bool:
    """chromadb + sentence-transformers 是否已安装。用 find_spec **只探测不导入**
    (导入 sentence_transformers 会拖入 torch,慢;状态查询要廉价)。"""
    import importlib.util
    return bool(
        importlib.util.find_spec("chromadb")
        and importlib.util.find_spec("sentence_transformers")
    )


def model_loaded() -> bool:
    """嵌入模型是否已载入内存(_embedder 的 lru_cache 是否已填充)。
    默认启动时为 False——只有建索引/检索真正用到时才载入。"""
    try:
        return _embedder.cache_info().currsize > 0  # type: ignore[attr-defined]
    except Exception:
        return False


def indexed_count() -> int:
    """活动书向量库已索引的片段数(0 = 空库/未建)。deps 缺失时返回 0,不抛。"""
    if not deps_available():
        return 0
    try:
        return _get_or_create().count()
    except Exception:
        return 0


def _reset_collection() -> None:
    """删掉旧 collection,避免重切章/重建后残留过期片段。"""
    try:
        _client().delete_collection(_COLLECTION)
    except Exception:
        pass


# 重建索引的进度(供前端轮询)。模块级单例,够用(单机单进程)。
_REINDEX_STATE: dict = {"status": "idle", "chapters": 0, "chunks": 0, "error": None}


def reindex_state() -> dict:
    return dict(_REINDEX_STATE)


def reindex_active_book() -> dict:
    """把活动书的全部章节(切片自 corpus_txt)重新嵌入入库。**重操作**:
    首次会触发嵌入模型加载(可能从 HuggingFace 下载 ~1.3GB),应在后台运行。
    会先清空旧 collection 再重建,保证与当前切章一致。"""
    from sqlalchemy import asc, select

    from ..books.library import active_paths
    from ..db import session_scope
    from .models import Chapter

    _REINDEX_STATE.update(status="running", chapters=0, chunks=0, error=None)
    try:
        if not deps_available():
            raise RuntimeError(
                "向量依赖未安装:请在 backend 下运行 "
                "`.venv/bin/python -m pip install chromadb sentence-transformers`"
            )
        corpus_path = active_paths()["corpus_txt"]
        if not corpus_path.exists():
            raise RuntimeError(f"未找到语料 {corpus_path} —— 请先切分本书")
        corpus = corpus_path.read_text(encoding="utf-8")
        with session_scope() as s:
            rows = s.execute(select(Chapter).order_by(asc(Chapter.number))).scalars().all()
            chapters = [
                (r.number, r.title, r.char_offset_start, r.char_offset_end) for r in rows
            ]
        if not chapters:
            raise RuntimeError("本书还没有章节 —— 请先切分")
        _reset_collection()
        n = index_chapters(chapters, corpus)  # 触发模型加载 + 全量嵌入
        _REINDEX_STATE.update(status="done", chapters=len(chapters), chunks=n)
        return {"chapters": len(chapters), "chunks_indexed": n}
    except Exception as exc:
        _REINDEX_STATE.update(status="failed", error=str(exc)[:300])
        raise
