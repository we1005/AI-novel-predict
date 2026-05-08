from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from . import interview as interview_pipe
from . import profile_builder
from . import simulator

router = APIRouter()


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------


class ProfileRebuildRequest(BaseModel):
    top_n: int = 20
    after_chapter: int | None = None
    entity_ids: list[int] | None = None


@router.post("/profiles/rebuild")
def profiles_rebuild(body: ProfileRebuildRequest):
    return profile_builder.rebuild(
        top_n=body.top_n,
        after_chapter=body.after_chapter,
        entity_ids=body.entity_ids,
    )


@router.get("/profiles")
def profiles_list():
    return profile_builder.list_profiles()


@router.get("/profiles/{entity_id}")
def profile_get(entity_id: int):
    p = profile_builder.get_profile(entity_id)
    if not p:
        raise HTTPException(404, "no profile — run /sim/profiles/rebuild")
    return p


# ---------------------------------------------------------------------------
# Interview
# ---------------------------------------------------------------------------


class InterviewRequest(BaseModel):
    character_id: int
    after_chapter: int
    question: str


@router.post("/interview")
def interview(req: InterviewRequest):
    def gen():
        for chunk in interview_pipe.stream_answer(
            entity_id=req.character_id,
            after_chapter=req.after_chapter,
            question=req.question,
        ):
            yield chunk

    return StreamingResponse(gen(), media_type="text/plain; charset=utf-8")


@router.get("/interview/history")
def interview_history(character_id: int | None = None, limit: int = 50):
    return interview_pipe.list_history(entity_id=character_id, limit=limit)


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------


class SimulateRequest(BaseModel):
    after_chapter: int
    n_rounds: int = 3
    n_characters: int = 5
    focus_characters: list[int] | None = None
    user_hints: str = ""


@router.post("/simulate")
def simulate(body: SimulateRequest):
    try:
        return simulator.run_simulation(
            after_chapter=body.after_chapter,
            n_rounds=body.n_rounds,
            n_characters=body.n_characters,
            focus_characters=body.focus_characters,
            user_hints=body.user_hints,
        )
    except RuntimeError as e:
        raise HTTPException(400, str(e))


@router.get("/simulate/runs")
def simulate_list(limit: int = 30):
    return simulator.list_runs(limit=limit)


@router.get("/simulate/runs/{run_id}")
def simulate_get(run_id: int):
    r = simulator.get_run(run_id)
    if not r:
        raise HTTPException(404)
    return r
