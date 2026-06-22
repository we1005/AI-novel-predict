from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from . import pipeline
from . import bilingual as bi
from . import revoice as rv

router = APIRouter()


@router.get("")
def get_style():
    return pipeline.get_profile() or {"profile": None}


class AnalyzeReq(BaseModel):
    sample_n: int = 8


@router.post("/analyze")
def analyze(body: AnalyzeReq | None = None):
    n = body.sample_n if body else 8
    try:
        return pipeline.analyze(sample_n=max(3, min(20, n)))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, str(e)[:240])


class ToggleReq(BaseModel):
    mimic_enabled: bool | None = None
    bilingual: bool | None = None


@router.put("/toggle")
def toggle(body: ToggleReq):
    out = pipeline.set_toggles(mimic_enabled=body.mimic_enabled, bilingual=body.bilingual)
    if out is None:
        raise HTTPException(404, "no style profile yet — analyze first")
    return out


# ---- Bilingual cross-translation continuation ----

class BilingualReq(BaseModel):
    brief: str
    after_chapter: int
    chapter_n: int | None = None


@router.post("/bilingual")
def bilingual_start(body: BilingualReq, background: BackgroundTasks):
    """Kick off the ZH/EN cross-translation pipeline in the background; returns a
    job id to poll. Runs ~5 LLM calls, so it can't be synchronous."""
    job_id = bi.create_job(body.brief, body.after_chapter, body.chapter_n)
    background.add_task(bi.run_and_store, job_id, body.brief, body.after_chapter, body.chapter_n)
    return {"id": job_id, "status": "writing"}


@router.get("/bilingual")
def bilingual_list():
    return bi.list_jobs()


@router.get("/bilingual/{job_id}")
def bilingual_get(job_id: int):
    out = bi.get_job(job_id)
    if out is None:
        raise HTTPException(404)
    return out


# ---- Re-voice (推翻文笔, 保留主干剧情) ----

class RevoiceReq(BaseModel):
    voice: str = "wangwen"          # wangwen / mimic / english
    source_chapter: int | None = None
    text: str | None = None


@router.post("/revoice")
def revoice_start(body: RevoiceReq, background: BackgroundTasks):
    try:
        job = rv.start_job(body.voice, body.source_chapter, body.text)
    except ValueError as e:
        raise HTTPException(400, str(e))
    background.add_task(rv.run_and_store, job["id"], job["text"], body.voice, job["chapter_n"])
    return {"id": job["id"], "status": "writing"}


@router.get("/revoice")
def revoice_list():
    return rv.list_jobs()


@router.get("/revoice/{job_id}")
def revoice_get(job_id: int):
    out = rv.get_job(job_id)
    if out is None:
        raise HTTPException(404)
    return out
