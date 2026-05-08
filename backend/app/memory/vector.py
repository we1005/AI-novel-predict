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
    for i, doc in enumerate(res["documents"][0]):
        meta = res["metadatas"][0][i]
        out.append({
            "chapter": meta.get("chapter"),
            "title": meta.get("title"),
            "chunk": meta.get("chunk"),
            "text": doc,
            "distance": res["distances"][0][i],
        })
    return out
