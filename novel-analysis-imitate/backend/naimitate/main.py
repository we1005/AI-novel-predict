"""novel-analysis-imitate 后端入口(Phase 0 脚手架)。

复用现有续写项目的 app 包(LLM/抽取/风格/笔法/生成内核),见 bootstrap。
本服务自身只负责:跨书 project 聚合 + 新分析层 + 融合/生成编排。
"""
from __future__ import annotations

from .bootstrap import ensure_app_importable
ensure_app_importable()  # 必须在 import app.* 之前

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from fastapi import BackgroundTasks  # noqa: E402

from app.books import library  # 复用现有多书库
from .project import store as project_store
from .project import orchestrate
from .analysis import beat, worldview, relationship, golden, pov

app = FastAPI(title="novel-analysis-imitate")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health():
    return {"ok": True, "service": "novel-analysis-imitate", "phase": 0}


@app.get("/books")
def books():
    """复用现有书库(backend/data/books)——分析的成员书从这里挑。"""
    return library.list_books()


class CreateProject(BaseModel):
    slug: str
    name: str
    intent: str = ""
    use_case: str = ""        # uc1 / uc2 / uc3 / uc4 / analysis
    member_book_slugs: list[str] = []


@app.post("/projects")
def create_project(body: CreateProject):
    return project_store.create_project(body.slug, body.name, body.intent,
                                        body.use_case, body.member_book_slugs)


@app.get("/projects")
def projects():
    return project_store.list_projects()


@app.get("/projects/{slug}")
def project(slug: str):
    return project_store.get_project(slug) or {"error": "not found"}


# ---- Phase 1 · 节拍分析(chapter_beat)----

class BeatReq(BaseModel):
    max_chapters: int | None = None   # 调试用:只扫前 N 章;None=全书


@app.post("/projects/{slug}/analyze-beats")
def analyze_beats(slug: str, body: BeatReq, background: BackgroundTasks):
    """后台串行对 project 各成员书跑 chapter_beat;轮询 /projects/{slug}/beat-job。"""
    background.add_task(orchestrate.run_project_beats, slug, max_chapters=body.max_chapters)
    return {"status": "started", "project": slug}


@app.get("/projects/{slug}/beat-job")
def beat_job(slug: str):
    return orchestrate.job_status(slug)


@app.post("/books/{slug}/analyze-beats")
def analyze_book_beats(slug: str, body: BeatReq, background: BackgroundTasks):
    """对单本书跑节拍分析(后台)。"""
    background.add_task(orchestrate.analyze_book_beats, slug, max_chapters=body.max_chapters)
    return {"status": "started", "book": slug}


@app.get("/books/{slug}/beats")
def book_beats(slug: str):
    """给前端可视化:逐章节拍曲线 + pacing 聚合卡。"""
    return beat.get_beats(slug)


# ---- Phase 1 · 全分析层(worldview / relationship / golden / pov)----

class LayerReq(BaseModel):
    layers: list[str] | None = None   # None=全层
    max_chapters: int | None = None


@app.post("/projects/{slug}/analyze")
def analyze_project(slug: str, body: LayerReq, background: BackgroundTasks):
    """后台串行对 project 各成员书跑(指定或全部)分析层。轮询 /beat-job。"""
    background.add_task(orchestrate.run_project_analysis, slug,
                        layers=body.layers, max_chapters=body.max_chapters)
    return {"status": "started", "project": slug, "layers": body.layers or orchestrate.ALL_LAYERS}


@app.post("/books/{slug}/analyze")
def analyze_book(slug: str, body: LayerReq, background: BackgroundTasks):
    """对单本书跑(指定或全部)分析层(后台)。"""
    background.add_task(orchestrate.analyze_book_all, slug,
                        layers=body.layers, max_chapters=body.max_chapters)
    return {"status": "started", "book": slug, "layers": body.layers or orchestrate.ALL_LAYERS}


@app.get("/books/{slug}/worldview")
def book_worldview(slug: str):
    return worldview.get_reveals(slug)


@app.get("/books/{slug}/relationships")
def book_relationships(slug: str):
    return relationship.get_events(slug)


@app.get("/books/{slug}/golden")
def book_golden(slug: str):
    return golden.get_steps(slug)


@app.get("/books/{slug}/pov")
def book_pov(slug: str):
    return pov.get_events(slug)


@app.get("/books/{slug}/analysis")
def book_analysis(slug: str):
    """汇总一本书的全部分析层,供前端一次拉取渲染。"""
    return {
        "slug": slug,
        "beats": beat.get_beats(slug),
        "worldview": worldview.get_reveals(slug),
        "relationships": relationship.get_events(slug),
        "golden": golden.get_steps(slug),
        "pov": pov.get_events(slug),
    }
