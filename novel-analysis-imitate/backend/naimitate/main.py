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
from .generate import usecases, compose, transplant, fusion
from .generate import technique as tech

app = FastAPI(title="novel-analysis-imitate")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health():
    return {"ok": True, "service": "novel-analysis-imitate", "phase": 0}


@app.get("/books")
def books(include_compose: bool = False):
    """真实源书列表(默认排除 compose 生成的虚拟书),并标注是否已分析。"""
    from app.db import get_engine
    from sqlalchemy import text as _t
    compose_slugs = {c["cslug"] for c in project_store.list_compose()}
    out = []
    for b in library.list_books():
        slug = b.get("slug")
        if not include_compose and slug in compose_slugs:
            continue
        # 轻量探测:该书 novel.db 是否有 chapter_beat 行(=已分析)
        analyzed = False
        n_beats = 0
        try:
            library.set_active(slug)
            with get_engine().begin() as c:
                n_beats = c.execute(_t("SELECT COUNT(*) FROM chapter_beat")).scalar() or 0
            analyzed = n_beats > 0
        except Exception:
            pass
        out.append({**b, "analyzed": analyzed, "n_beats": n_beats})
    # 已分析的排前面
    out.sort(key=lambda x: (not x["analyzed"], x.get("slug") or ""))
    return out


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


# ---- Phase 2+ · 生成用例(compose 虚拟书)----

class ChapterOutline(BaseModel):
    chapter_index: int | None = None
    title: str | None = None
    summary: str = ""
    beats: list[str] = []
    must_include: list[str] = []
    word_target: int | None = None
    directives: str = ""


class UC2Req(BaseModel):
    cslug: str
    voice_source: str
    chapters: list[ChapterOutline]
    project_slug: str = ""
    user_hints: str = ""
    overwrite: bool = False


class UC1Req(UC2Req):
    fuse_sources: list[str] = []


class UC4Req(UC2Req):
    technique_template: dict | None = None
    technique_source: str = ""   # 留空=用 voice_source;从该书分析层自动蒸馏技法模板


class GenReq(BaseModel):
    chapter_index: int
    skip_reviews: bool = False


class FuseReq(BaseModel):
    source_slugs: list[str]


@app.post("/projects/{slug}/fuse")
def fuse_project(slug: str, body: FuseReq, background: BackgroundTasks):
    """后台跨书融合(MODEL_STRONG 蒸馏 fused_worldview/style/technique)。轮询 /fusion。"""
    background.add_task(fusion.build_all, slug, body.source_slugs)
    return {"status": "started", "project": slug, "sources": body.source_slugs}


@app.get("/projects/{slug}/fusion")
def project_fusion(slug: str):
    return fusion.get_fusion(slug)


@app.get("/compose")
def list_compose():
    return project_store.list_compose()


@app.post("/compose/uc2")
def compose_uc2(body: UC2Req):
    return usecases.uc2_voice_transfer(
        cslug=body.cslug, voice_source=body.voice_source,
        chapters=[c.model_dump() for c in body.chapters],
        project_slug=body.project_slug, user_hints=body.user_hints, overwrite=body.overwrite)


@app.post("/compose/uc1")
def compose_uc1(body: UC1Req):
    return usecases.uc1_fused_world_voice(
        cslug=body.cslug, voice_source=body.voice_source, fuse_sources=body.fuse_sources,
        chapters=[c.model_dump() for c in body.chapters],
        project_slug=body.project_slug, user_hints=body.user_hints, overwrite=body.overwrite)


@app.post("/compose/uc4")
def compose_uc4(body: UC4Req):
    return usecases.uc4_technique_injected(
        cslug=body.cslug, voice_source=body.voice_source,
        chapters=[c.model_dump() for c in body.chapters],
        technique_template=body.technique_template, technique_source=body.technique_source,
        project_slug=body.project_slug, user_hints=body.user_hints, overwrite=body.overwrite)


@app.post("/books/{slug}/technique")
def build_technique(slug: str, n_chapters: int = 6):
    """从该书分析层蒸馏 technique_template(导演手册)。"""
    return tech.build_template(slug, n_chapters=n_chapters)


@app.get("/books/{slug}/technique")
def get_technique(slug: str):
    return tech.get_template(slug) or {"error": "未蒸馏 — 先 POST /books/{slug}/technique"}


class UC3Req(BaseModel):
    cslug: str
    voice_source: str           # 目标世界观的文风源(如克苏鲁组某书)
    plot_sources: list[str]     # 提供剧情母核的源书(A/B/C)
    anchor_world: str           # 目标世界观设定描述
    n_chapters: int = 3
    top_n_per_source: int = 8
    project_slug: str = ""
    overwrite: bool = False


@app.post("/compose/uc3")
def compose_uc3(body: UC3Req):
    return transplant.uc3_transplant(
        cslug=body.cslug, voice_source=body.voice_source, plot_sources=body.plot_sources,
        anchor_world=body.anchor_world, n_chapters=body.n_chapters,
        top_n_per_source=body.top_n_per_source, project_slug=body.project_slug,
        overwrite=body.overwrite)


@app.post("/compose/{cslug}/generate")
def compose_generate(cslug: str, body: GenReq, background: BackgroundTasks):
    """后台生成某章(写章较慢);轮询 /compose/{cslug}/export 看产物。"""
    background.add_task(usecases.generate_chapter, cslug, body.chapter_index,
                        skip_reviews=body.skip_reviews)
    return {"status": "started", "cslug": cslug, "chapter_index": body.chapter_index}


@app.get("/compose/{cslug}/export")
def compose_export(cslug: str):
    return compose.export_chapters(cslug)
