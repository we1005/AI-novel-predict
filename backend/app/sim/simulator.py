"""ChapterSimulator — N-round multi-agent simulation that produces a chapter.

Pipeline (per /predict/simulate request):
  1. Pick the active cast (5-8 characters by importance + foreshadow weight)
  2. Snapshot initial scene state from the structured DB at after_chapter
  3. For each round, run DecisionAgent in parallel (one LLM call per character)
  4. Append actions to rounds_json; the *next* round's prompt sees them
  5. After N rounds, ReportAgent writes a coherent chapter from the log
  6. Persist the chapter as a ``status="draft"`` ChapterDraft (NOT approved) and
     link it on SimulationRun.chapter_draft_id, so the speculative output can
     flow into the EXISTING gated reviewer/回灌 chain — canonical EntityState is
     only updated when the user *accepts* the draft (see extract_one_chapter).

Cost budget (with qwen3.5-flash):
  ~5 chars × 3 rounds = 15 decision calls @ ~$0.003 = ~$0.05
  + 1 ReportAgent @ ~$0.02 = ~$0.07 per simulation
"""

from __future__ import annotations

import copy
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any

from sqlalchemy import asc, desc, select

from ..config import MODEL_FAST, MODEL_STRONG
from ..db import session_scope
from ..llm import client as llm
from ..llm.prompts.decision import DECISION_SYSTEM, DECISION_TOOL
from ..llm.prompts.sim_report import REPORT_SYSTEM
from ..memory.models import (
    CharacterProfile,
    ChapterDraft,
    Entity,
    EntityState,
    Foreshadowing,
    PlotPoint,
    Relationship,
    SimulationRun,
    WorldRule,
)
from .profile_builder import get_profile, rebuild as rebuild_profiles


# ---------------------------------------------------------------------------
# Cast selection & snapshot
# ---------------------------------------------------------------------------

def _select_cast(after_chapter: int, n_characters: int,
                 focus_ids: list[int] | None) -> list[Entity]:
    """Pick active cast: importance + foreshadow involvement + relationships
    + the user's focus list. Always include the protagonist if available."""

    with session_scope() as s:
        people = s.execute(
            select(Entity)
            .where(Entity.type == "person", Entity.first_appear_chapter <= after_chapter)
            .order_by(desc(Entity.importance))
        ).scalars().all()

        # protagonist always in
        protagonist = next((p for p in people if p.role == "protagonist"), None)
        if not protagonist and people:
            protagonist = people[0]

        out: list[Entity] = []
        seen: set[int] = set()
        if protagonist:
            out.append(protagonist)
            seen.add(protagonist.id)

        # focus first
        for eid in (focus_ids or []):
            if eid in seen:
                continue
            ent = next((p for p in people if p.id == eid), None)
            if ent:
                out.append(ent)
                seen.add(ent.id)
                if len(out) >= n_characters:
                    return out

        # then by importance
        for p in people:
            if p.id in seen:
                continue
            out.append(p)
            seen.add(p.id)
            if len(out) >= n_characters:
                break
        return out


def _ensure_profiles(cast: list[Entity], after_chapter: int) -> None:
    """Lazy-build profiles for any cast member missing one (or stale by 200 chap)."""

    missing: list[int] = []
    with session_scope() as s:
        for ent in cast:
            row = s.execute(
                select(CharacterProfile).where(CharacterProfile.entity_id == ent.id).limit(1)
            ).scalar_one_or_none()
            if (
                row is None
                or row.last_built_chapter is None
                # 修复 E4(红蓝对抗):边界 `>200` 漏掉"建于150、模拟350(差正好200)"的陈旧档案 → 改 `>=`。
                # (每轮状态快照 / 仿真产物回灌 / 未来章泄漏 属更大的仿真质量改造,见 docs 待修。)
                or abs((row.last_built_chapter or 0) - after_chapter) >= 200
            ):
                missing.append(ent.id)
    if missing:
        rebuild_profiles(entity_ids=missing, after_chapter=after_chapter)


def _initial_state(after_chapter: int, cast: list[Entity]) -> dict[str, Any]:
    """Latest known states for the cast as of after_chapter, plus shared
    world context (open mysteries, open foreshadowings, recent plot points)."""

    cast_ids = [c.id for c in cast]
    with session_scope() as s:
        # latest entity state per character
        char_state: dict[int, dict] = {}
        for cid in cast_ids:
            st = s.execute(
                select(EntityState)
                .where(EntityState.entity_id == cid, EntityState.chapter <= after_chapter)
                .order_by(desc(EntityState.chapter))
                .limit(1)
            ).scalar_one_or_none()
            char_state[cid] = {
                "as_of_chapter": st.chapter if st else None,
                "state": st.state_json if st else {},
                "last_change_note": st.note if st else None,
            }

        # cast-relevant open foreshadows
        fs_open = s.execute(
            select(Foreshadowing).where(
                Foreshadowing.status == "open",
                Foreshadowing.planted_chapter <= after_chapter,
            ).order_by(asc(Foreshadowing.planted_chapter))
        ).scalars().all()
        fs_dump = []
        for f in fs_open:
            related = list(f.related_entity_ids_json or [])
            if any(eid in cast_ids for eid in related):
                fs_dump.append({
                    "id": f.id,
                    "type": f.type,
                    "planted": f.planted_chapter,
                    "description": (f.description or "")[:200],
                    "involves": related,
                })

        # recent plot points
        plots = s.execute(
            select(PlotPoint)
            .where(PlotPoint.chapter <= after_chapter, PlotPoint.importance >= 60)
            .order_by(desc(PlotPoint.chapter))
            .limit(8)
        ).scalars().all()
        plot_dump = [
            {"chapter": p.chapter, "summary": (p.summary or "")[:200]}
            for p in reversed(plots)
        ]

        # cast-pair relationships (LLM-labeled)
        rels = s.execute(
            select(Relationship).where(
                Relationship.from_entity_id.in_(cast_ids),
                Relationship.to_entity_id.in_(cast_ids),
            )
        ).scalars().all()
        ent_by_id = {e.id: e.name for e in s.execute(select(Entity)).scalars().all()}
        rel_dump = [
            {
                "from": ent_by_id.get(r.from_entity_id),
                "to": ent_by_id.get(r.to_entity_id),
                "label": r.label,
                "description": (r.description or "")[:160],
            }
            for r in rels
        ]

        # world rules (cap to brief list)
        world = s.execute(select(WorldRule).limit(20)).scalars().all()
        world_dump = [{"term": w.term, "def": (w.definition or "")[:120]} for w in world]

    return {
        "char_state": {ent_by_id.get(cid, str(cid)): state for cid, state in char_state.items()},
        "open_foreshadowings": fs_dump,
        "recent_plot_points": plot_dump,
        "cast_relationships": rel_dump,
        "world_rules_brief": world_dump,
    }


# ---------------------------------------------------------------------------
# E4:每轮活状态(non-frozen)与产物落库辅助(均为纯函数,可单测)
# ---------------------------------------------------------------------------

def _fold_round_into_state(char_state: dict, actions: list[dict], round_no: int) -> dict:
    """把本轮各角色的公开动作累积进其结构化状态(``events_during_sim`` 轨迹)。

    修复 E4:此前 ``initial_state`` 全程冻结(只算一次第 N 章快照),每轮
    ``my_current_state`` 都是同一份初始值——角色看不到自己上一轮做了什么的
    *结构化*状态(只能从全局动作日志里自己捞)。折叠后,下一轮各角色的
    ``my_current_state`` 会带上其本人迄今为止的演进轨迹。

    就地修改并返回 ``char_state``(返回值便于测试)。
    """
    for a in actions or []:
        name = a.get("character")
        if not name:
            continue
        slot = char_state.setdefault(name, {})
        if not isinstance(slot, dict):
            slot = {"state": slot}
            char_state[name] = slot
        trail = slot.setdefault("events_during_sim", [])
        trail.append({
            "round": round_no,
            "kind": a.get("kind"),
            "content": (a.get("content") or "")[:120],
        })
    return char_state


def _chapter_title_from_text(text: str, after_chapter: int) -> str:
    """从 ReportAgent 正文首行抽章节标题;无则用默认「第 N+1 章」。"""
    for line in (text or "").splitlines():
        line = line.strip()
        if line:
            return line[:80]
    return f"第 {after_chapter + 1} 章"


# ---------------------------------------------------------------------------
# Per-character decision call
# ---------------------------------------------------------------------------

def _decide_one(
    character: Entity,
    profile: dict,
    initial_state: dict,
    rounds_so_far: list[dict],
    cast_names: list[str],
    after_chapter: int,
    user_hints: str,
    round_index: int,
) -> tuple[dict | None, float]:
    """Run a single LLM decision call for one character. Returns (action, cost)."""

    # Filter the character's "known" subgraph: their profile is theirs, their
    # state row is theirs, but they only see PUBLIC actions of others (the
    # full rounds_so_far). They don't see other characters' private profiles.
    known = {
        "name": character.name,
        "profile": {
            "bio": profile.get("bio"),
            "desires": profile.get("desires"),
            "fears": profile.get("fears"),
            "moral_compass": profile.get("moral_compass"),
            "voice_style": profile.get("voice_style"),
            "typical_actions": profile.get("typical_actions"),
            "relationships": profile.get("relationships_summary"),
            "secrets_known": profile.get("secrets_known"),
            "secrets_hidden": profile.get("secrets_hidden"),
            "arc_so_far": profile.get("arc_so_far"),
        },
        "my_current_state": initial_state["char_state"].get(character.name, {}),
        "shared_open_foreshadowings": initial_state["open_foreshadowings"],
        "recent_plot_points_known_to_all": initial_state["recent_plot_points"],
        "world_rules_brief": initial_state["world_rules_brief"],
        "cast_present": cast_names,
        "after_chapter": after_chapter,
    }

    blocks = [
        llm.cached_block("【你的档案与已知信息】\n" + llm.stable_json(known)),
    ]
    if user_hints.strip():
        blocks.append(llm.cached_block("【作者偏好（导演备注）】\n" + user_hints.strip()))

    rounds_text = json.dumps(rounds_so_far, ensure_ascii=False, indent=2)
    user = (
        f"# 现在是第 {round_index + 1} 轮\n\n"
        f"已经发生的所有公开动作（你能看到的）：\n{rounds_text or '（这是第一轮，尚无动作）'}\n\n"
        f"你（{character.name}）现在做什么？调用 take_action。"
    )

    # JSON-in-text, not forced tool_choice: sim.decide runs on doubao-lite (volc
    # reasoning) which silently drops forced-tool output → character's action
    # vanishes from the round. Embed the schema; parse from content.
    _hint = ("\n\n# 输出格式（严格 · 覆盖前述任何「调用工具」指示）\n"
             "只输出一个 JSON 对象，不要任何其它文字、不要 markdown 围栏。必须严格符合此 JSON Schema：\n"
             + json.dumps(DECISION_TOOL["input_schema"], ensure_ascii=False))
    try:
        resp = llm.call(
            agent="sim.decide",
            model=MODEL_FAST,
            system=[{"type": "text", "text": DECISION_SYSTEM + _hint}, *blocks],
            messages=[{"role": "user", "content": user}],
            max_tokens=2000,
            temperature=0.85,
            top_p=0.95,
        )
    except Exception as exc:
        return None, 0.0

    out = (resp.tool_use or {}).get("input", {}) or {}
    if not out and resp.text:
        try:
            from json_repair import repair_json
            import re as _re
            out = json.loads(repair_json(_re.sub(r"```json|```", "", resp.text))) or {}
        except Exception:
            out = {}
    if not isinstance(out, dict) or not out.get("kind") or not out.get("content"):
        return None, resp.cost_usd

    # Truncate runaway output
    out["content"] = (out.get("content") or "")[:240]
    out["reasoning"] = (out.get("reasoning") or "")[:160]
    out["character"] = character.name
    out["character_id"] = character.id

    return out, resp.cost_usd


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def _report(simulation_id: int, sim_run: dict, after_chapter: int) -> tuple[str, float]:
    """Run ReportAgent: synthesize the action log into chapter prose."""

    blocks = [
        llm.cached_block("【仿真元信息】\n" + llm.stable_json({
            "after_chapter": after_chapter,
            "n_rounds": sim_run["n_rounds"],
            "cast": sim_run["cast_names"],
            "user_hints": sim_run.get("user_hints"),
        })),
        llm.cached_block("【仿真行动日志】\n" + llm.stable_json(sim_run["rounds_json"])),
        llm.cached_block("【参演角色档案概要】\n" + llm.stable_json(sim_run["cast_profiles_brief"])),
    ]
    user = (
        f"请把上述仿真综合成一段约 3000 字的中文小说章节。"
        f"按行动日志顺序展开，加必要的场景与心理描写连接。"
        f"开头第一行写章节标题（第 {after_chapter + 1} 章 ……），空行后正文。"
    )
    try:
        resp = llm.call(
            agent="sim.report",
            model=MODEL_STRONG,
            system=[{"type": "text", "text": REPORT_SYSTEM}, *blocks],
            messages=[{"role": "user", "content": user}],
            max_tokens=8000,
            temperature=0.7,
        )
    except Exception:
        return "", 0.0
    return resp.text or "", resp.cost_usd


# ---------------------------------------------------------------------------
# Top-level orchestrator
# ---------------------------------------------------------------------------

def run_simulation(
    *,
    after_chapter: int,
    n_rounds: int = 3,
    n_characters: int = 5,
    focus_characters: list[int] | None = None,
    user_hints: str = "",
) -> dict[str, Any]:
    n_rounds = max(1, min(8, n_rounds))
    n_characters = max(2, min(8, n_characters))

    # Create the run row early so the user can poll status.
    with session_scope() as s:
        run = SimulationRun(
            after_chapter=after_chapter,
            n_rounds=n_rounds,
            n_characters=n_characters,
            focus_characters=focus_characters or [],
            user_hints=user_hints or None,
            rounds_json=[],
            status="simulating",
            created_at=datetime.utcnow(),
        )
        s.add(run)
        s.flush()
        sim_id = run.id

    total_cost = 0.0
    try:
        cast = _select_cast(after_chapter, n_characters, focus_characters)
        if not cast:
            raise RuntimeError("no characters selected — populate entities first")

        _ensure_profiles(cast, after_chapter)
        profiles_by_id: dict[int, dict] = {}
        for ent in cast:
            p = get_profile(ent.id) or {}
            profiles_by_id[ent.id] = p

        initial_state = _initial_state(after_chapter, cast)
        cast_names = [c.name for c in cast]
        # E4:活状态(每轮折叠动作),不再全程冻结 initial_state。
        live_state = copy.deepcopy(initial_state)

        rounds: list[dict] = []
        for r in range(n_rounds):
            actions: list[dict] = []
            with ThreadPoolExecutor(max_workers=min(len(cast), 6)) as ex:
                futs = {
                    ex.submit(
                        _decide_one,
                        char, profiles_by_id.get(char.id) or {},
                        live_state, rounds, cast_names,
                        after_chapter, user_hints, r,
                    ): char
                    for char in cast
                }
                for fut in as_completed(futs):
                    try:
                        action, cost = fut.result()
                    except Exception:
                        action, cost = None, 0.0
                    total_cost += cost
                    if action:
                        actions.append(action)

            # Stable order: by character name to keep round logs deterministic
            actions.sort(key=lambda a: cast_names.index(a["character"]) if a["character"] in cast_names else 99)
            # E4:折叠本轮动作进活状态 → 下一轮各角色 my_current_state 带上自身演进轨迹;
            # 并把本轮快照存进 round_record(供报告/前端看状态演进,模型注释早已预留该字段)。
            _fold_round_into_state(live_state["char_state"], actions, r + 1)
            round_record = {
                "round": r + 1,
                "actions": actions,
                "state_snapshot": copy.deepcopy(live_state["char_state"]),
            }
            rounds.append(round_record)

            # persist incrementally so a polling client can see progress
            with session_scope() as s:
                row = s.get(SimulationRun, sim_id)
                if row:
                    row.rounds_json = list(rounds)
                    row.cost_usd = total_cost
                    row.updated_at = datetime.utcnow()

        # ReportAgent synthesizes
        with session_scope() as s:
            row = s.get(SimulationRun, sim_id)
            if row:
                row.status = "reporting"

        cast_profiles_brief = [
            {
                "name": ent.name,
                "role": ent.role,
                "voice_style": (profiles_by_id.get(ent.id) or {}).get("voice_style"),
                "desires": (profiles_by_id.get(ent.id) or {}).get("desires"),
            }
            for ent in cast
        ]
        sim_run_payload = {
            "n_rounds": n_rounds,
            "rounds_json": rounds,
            "cast_names": cast_names,
            "cast_profiles_brief": cast_profiles_brief,
            "user_hints": user_hints,
        }
        text, report_cost = _report(sim_id, sim_run_payload, after_chapter)
        total_cost += report_cost

        # E4(c):把仿真产物落成 status="draft" 的 ChapterDraft 并回填 chapter_draft_id,
        # 使其能进入 *既有的、有人审 gate 的* 复审/回灌链(草稿被接受后才 extract_one_chapter
        # 回灌 canonical EntityState)。**刻意不**在此静默回灌——仿真是假设性的,直接写回真值
        # 会用推测内容污染记忆,比原 bug 更糟;正确做法是经 draft→人审→接受 这条既有通路。
        draft_id: int | None = None
        with session_scope() as s:
            row = s.get(SimulationRun, sim_id)
            if text.strip():
                draft = ChapterDraft(
                    outline_run_id=None,
                    chapter_index=after_chapter + 1,
                    title=_chapter_title_from_text(text, after_chapter),
                    status="draft",
                    attempts_json=[{"source": "simulation", "simulation_run_id": sim_id}],
                    final_text=text,
                    cost_usd=total_cost,
                )
                s.add(draft)
                s.flush()
                draft_id = draft.id
            if row:
                row.final_text = text
                row.chapter_draft_id = draft_id
                row.cost_usd = total_cost
                row.status = "done"
                row.updated_at = datetime.utcnow()

        return {
            "id": sim_id,
            "status": "done",
            "n_rounds": n_rounds,
            "cast": cast_names,
            "rounds": rounds,
            "final_text": text,
            "chapter_draft_id": draft_id,
            "cost_usd": round(total_cost, 5),
        }
    except Exception as exc:
        with session_scope() as s:
            row = s.get(SimulationRun, sim_id)
            if row:
                row.status = "failed"
                row.error = str(exc)[:500]
                row.cost_usd = total_cost
                row.updated_at = datetime.utcnow()
        raise


def list_runs(limit: int = 30) -> list[dict[str, Any]]:
    with session_scope() as s:
        rows = s.execute(
            select(SimulationRun).order_by(desc(SimulationRun.id)).limit(limit)
        ).scalars().all()
        return [
            {
                "id": r.id,
                "after_chapter": r.after_chapter,
                "n_rounds": r.n_rounds,
                "n_characters": r.n_characters,
                "status": r.status,
                "cost_usd": r.cost_usd,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]


def get_run(run_id: int) -> dict[str, Any] | None:
    with session_scope() as s:
        r = s.get(SimulationRun, run_id)
        if not r:
            return None
        cast_names: list[str] = []
        if r.focus_characters:
            ent_by_id = {e.id: e.name for e in s.execute(select(Entity)).scalars().all()}
            cast_names = [ent_by_id.get(eid, str(eid)) for eid in r.focus_characters]
        return {
            "id": r.id,
            "after_chapter": r.after_chapter,
            "n_rounds": r.n_rounds,
            "n_characters": r.n_characters,
            "focus_characters": r.focus_characters or [],
            "cast_names": cast_names,
            "user_hints": r.user_hints,
            "rounds_json": r.rounds_json or [],
            "final_text": r.final_text,
            "status": r.status,
            "error": r.error,
            "cost_usd": r.cost_usd,
            "chapter_draft_id": r.chapter_draft_id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
