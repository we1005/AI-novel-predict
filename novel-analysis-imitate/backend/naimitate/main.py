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

from app.books import library  # 复用现有多书库
from .project import store as project_store

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
