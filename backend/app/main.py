from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .books.api import router as books_router
from .books.library import ensure_layout
from .draft.api import router as draft_router
from .sim.api import router as sim_router
from .graph.api import router as graph_router
from .ingest.api import router as ingest_router
from .memory.api import router as memory_router
from .memory.schema_init import init_schema
from .monitor.api import router as monitor_router
from .mysteries.api import router as mysteries_router
from .outline.api import router as outline_router
from .predict.api import router as predict_router
from .settings.api import router as settings_router
from .style.api import router as style_router
from .repo.api import router as repo_router
from .craft.api import router as craft_router

app = FastAPI(title="Novel Writer API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    # 本地开发:放行 localhost 与 127.0.0.1 的任意端口(此前只放 localhost:3100,
    # 从 127.0.0.1:3100 打开前端会被 CORS 拦)。
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    # 1) Migrate legacy data/novel.db → data/books/<slug>/novel.db on first run.
    ensure_layout()
    # 2) Now that the active book is settled, init schema in its DB. Subsequent
    #    book switches hit init_schema again via db.get_engine() lazily.
    try:
        init_schema()
    except RuntimeError:
        # No books imported yet — that's fine. Schema gets built when the
        # first book is imported.
        pass


@app.get("/health")
def health() -> dict:
    return {"ok": True}


app.include_router(ingest_router, prefix="/ingest", tags=["ingest"])
app.include_router(memory_router, prefix="/memory", tags=["memory"])
app.include_router(predict_router, prefix="/predict", tags=["predict"])
app.include_router(graph_router, prefix="/graph", tags=["graph"])
app.include_router(monitor_router, prefix="/monitor", tags=["monitor"])
app.include_router(mysteries_router, prefix="/mysteries", tags=["mysteries"])
app.include_router(outline_router, prefix="/outline", tags=["outline"])
app.include_router(draft_router, prefix="/draft", tags=["draft"])
app.include_router(sim_router, prefix="/sim", tags=["sim"])
app.include_router(settings_router, prefix="/settings", tags=["settings"])
app.include_router(style_router, prefix="/style", tags=["style"])
app.include_router(books_router, prefix="/books", tags=["books"])
app.include_router(repo_router, prefix="/repo", tags=["repo"])
app.include_router(craft_router, prefix="/craft", tags=["craft"])
