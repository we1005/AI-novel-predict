"""书稿版本控制 API：初始化/状态/历史/撤回/分支/物化。"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from . import store

router = APIRouter()


@router.get("/status")
def status():
    d = store.repo_dir()
    return {
        "repo": str(d),
        "initialized": (d / ".git").exists(),
        "increments": len(list((d / "memory" / "increments").glob("ch*.json"))) if (d / "memory" / "increments").exists() else 0,
        "chapters": sorted(int(p.stem[2:].split(".")[0]) for p in (d / "manuscript").glob("ch*.zh.md")) if (d / "manuscript").exists() else [],
    }


@router.post("/init")
def init():
    return store.init_repo()


@router.get("/history")
def history(path: str | None = None, limit: int = 50):
    return {"commits": store.history(path=path, limit=limit)}


@router.post("/baseline")
def snapshot_baseline():
    counts = store.dump_baseline()
    res = store.commit("baseline: 重新快照派生记忆")
    return {"counts": counts, "commit": res}


@router.post("/materialize")
def materialize():
    """从 git 内容重建 SQLite 派生记忆（DB 脏了/回退后调用）。"""
    return store.materialize()


class ChapterReq(BaseModel):
    chapter: int


@router.post("/revert-chapter")
def revert_chapter(body: ChapterReq):
    """撤回某章：删正文+增量 → 重新物化（记忆与正文一起干净回退）。"""
    return store.revert_chapter(body.chapter)


class BranchReq(BaseModel):
    name: str


@router.post("/branch")
def branch(body: BranchReq):
    return store.create_branch(body.name)
