"""书稿版本控制层（Git 管"源"，SQLite 当可重建缓存）。

设计（详见架构文档）：每本书一个独立 git 仓 `data/books/<slug>/repo/`，
三棵树——manuscript/(正文中英)、outline/(大纲)、memory/(baseline 不可变基线 +
increments/ 每章抽取增量)。SQLite 的"派生记忆"表由 git 内容**确定性物化**出来：

    记忆 = baseline(corpus 1-156)  ⊕  按章号顺序重放各 increment

于是"撤回第 N 章"= 删 increments/chN.json + manuscript/chN.* → 重新物化；
importance 等累加量在重放时自然重建，删掉某章其贡献即消失。novel.db 不进仓
（派生缓存，可重建），书稿仓可独立 push 到自己的 GitHub remote。
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from ..db import session_scope
from ..books.library import active_paths
from ..memory.models import (
    Entity, Foreshadowing, Mystery, EntityState, PlotPoint, WorldRule, Relationship,
    ChapterDraft, BilingualDraft,
)

# 派生记忆表，按 FK 依赖排序（载入正序、清空逆序）。chapters/chapter_fts/chapter_drafts
# 不在此列：corpus 文本与正文稿各有其源，物化只重建"抽取出来的记忆"。
_MEMORY_MODELS = [Entity, Foreshadowing, Mystery, EntityState, PlotPoint, WorldRule, Relationship]
_MODEL_BY_NAME = {m.__tablename__: m for m in _MEMORY_MODELS}


# --------------------------------------------------------------------------- paths / git
def repo_dir() -> Path:
    d = Path(active_paths()["dir"]) / "repo"
    return d


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)


def init_repo() -> dict[str, Any]:
    """git init 书稿仓 + 目录骨架 + .gitignore（排除派生的 .db 缓存）。幂等。"""
    d = repo_dir()
    d.mkdir(parents=True, exist_ok=True)
    if not (d / ".git").exists():
        _git(["init"], d)
        _git(["config", "user.email", "mobi@local"], d)
        _git(["config", "user.name", "mobi"], d)
    (d / ".gitignore").write_text(
        "# 派生缓存，由 git 内容物化重建，不入版本库\nnovel.db\n*.db-wal\n*.db-shm\n*.sqlite*\nchroma/\n",
        encoding="utf-8",
    )
    for sub in ("manuscript", "outline", "memory/baseline", "memory/increments"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    return {"repo": str(d), "git": (d / ".git").exists()}


def commit(message: str) -> dict[str, Any]:
    d = repo_dir()
    if not (d / ".git").exists():
        init_repo()
    _git(["add", "-A"], d)
    r = _git(["commit", "-m", message], d)
    return {"ok": r.returncode == 0, "msg": message, "out": (r.stdout + r.stderr)[-300:]}


# --------------------------------------------------------------------------- serialize
def _row_to_dict(row) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for c in row.__table__.columns:
        v = getattr(row, c.name)
        out[c.name] = v.isoformat() if isinstance(v, datetime) else v
    return out


def _dict_to_kwargs(model, d: dict[str, Any]) -> dict[str, Any]:
    kw: dict[str, Any] = {}
    for c in model.__table__.columns:
        if c.name not in d:
            continue
        v = d[c.name]
        if isinstance(v, str) and c.name.endswith(("_at",)) and v:
            try:
                v = datetime.fromisoformat(v)
            except ValueError:
                v = None
        kw[c.name] = v
    return kw


# --------------------------------------------------------------------------- dump
def dump_baseline() -> dict[str, int]:
    """把当前"派生记忆"全表导出为 memory/baseline/<table>.json（作不可变基线）。"""
    base = repo_dir() / "memory" / "baseline"
    base.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    with session_scope() as s:
        for m in _MEMORY_MODELS:
            rows = s.execute(select(m)).scalars().all()
            data = [_row_to_dict(r) for r in rows]
            (base / f"{m.__tablename__}.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            counts[m.__tablename__] = len(data)
    return counts


def dump_manuscript(chapter: int) -> dict[str, Any]:
    """导出某章正文：manuscript/ch<N>.zh.md（已过审中文）+ ch<N>.en.md（双语英文）。"""
    man = repo_dir() / "manuscript"
    man.mkdir(parents=True, exist_ok=True)
    written = []
    with session_scope() as s:
        d = s.execute(select(ChapterDraft).where(ChapterDraft.chapter_index == chapter)
                      .order_by(ChapterDraft.id.desc())).scalars().first()
        if d and (d.final_text or "").strip():
            (man / f"ch{chapter}.zh.md").write_text(
                f"# 第{chapter}章 {d.title or ''}\n\n{d.final_text.strip()}\n", encoding="utf-8")
            written.append("zh")
        b = s.execute(select(BilingualDraft).where(BilingualDraft.chapter == chapter,
                      BilingualDraft.status == "done").order_by(BilingualDraft.id.desc())).scalars().first()
        if b and (b.final_en or "").strip():
            (man / f"ch{chapter}.en.md").write_text(
                f"# Chapter {chapter}\n\n{b.final_en.strip()}\n", encoding="utf-8")
            written.append("en")
    return {"chapter": chapter, "written": written}


def dump_increment(chapter: int, raw_outputs: dict[str, Any]) -> dict[str, Any]:
    """保存某章的抽取增量（6-agent 原始结构化输出）到 memory/increments/ch<N>.json。

    这是"撤回/重写本章"的最小单元：删它=撤回该章记忆贡献；物化时按章号重放它。
    """
    inc = repo_dir() / "memory" / "increments"
    inc.mkdir(parents=True, exist_ok=True)
    payload = {"chapter": chapter, "outputs": raw_outputs}
    (inc / f"ch{chapter}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"chapter": chapter, "agents": list(raw_outputs.keys())}


# --------------------------------------------------------------------------- materialize
def _wipe_memory(s) -> None:
    for m in reversed(_MEMORY_MODELS):  # 逆 FK 顺序删
        s.query(m).delete()


def materialize() -> dict[str, Any]:
    """从 git 内容确定性重建派生记忆：清空记忆表 → 载入 baseline → 按章号重放
    increments（复用线上同一套 _persist_dispatch，importance 等累加量随之重建）。

    DB 脏了/坏了，调它即可回到与 git 一致的干净状态。
    """
    from ..ingest.extract import _persist_dispatch
    base = repo_dir() / "memory" / "baseline"
    inc_dir = repo_dir() / "memory" / "increments"
    report = {"baseline": {}, "increments": 0}

    with session_scope() as s:
        _wipe_memory(s)
        # 1) 载入 baseline 全表
        for m in _MEMORY_MODELS:
            f = base / f"{m.__tablename__}.json"
            if not f.exists():
                continue
            data = json.loads(f.read_text(encoding="utf-8"))
            for d in data:
                s.add(m(**_dict_to_kwargs(m, d)))
            report["baseline"][m.__tablename__] = len(data)
        s.flush()

    # 2) 按章号顺序重放每章增量（每章一个事务，复用线上落库逻辑）
    files = sorted(inc_dir.glob("ch*.json"),
                   key=lambda p: int("".join(ch for ch in p.stem[2:] if ch.isdigit()) or 0))
    for f in files:
        payload = json.loads(f.read_text(encoding="utf-8"))
        ch = payload.get("chapter")
        outs = payload.get("outputs") or {}
        with session_scope() as s:
            for name in ("entity", "foreshadow", "state", "plot", "world", "mystery"):
                if name in outs:
                    _persist_dispatch(name, s, outs[name], batch_id=0, chapter_range=(ch, ch))
        report["increments"] += 1
    return report


def snapshot_chapter(chapter: int, message: str | None = None) -> dict[str, Any]:
    """一章定稿后：导出正文(zh/en) + commit（增量 ch<N>.json 已由回灌写好，git add -A 一并收）。

    "写作流程接版本控制"的入口：每章过审→回灌(落增量)→交织英文→调它→一次 commit。
    """
    init_repo()
    dump_manuscript(chapter)
    return commit(message or f"ch{chapter}: 定稿(中英) + 抽取增量")


def history(path: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """git 提交历史（可按文件过滤，如 manuscript/ch200.zh.md）。"""
    d = repo_dir()
    if not (d / ".git").exists():
        return []
    args = ["log", f"-{limit}", "--pretty=format:%h\t%ad\t%s", "--date=short"]
    if path:
        args += ["--", path]
    r = _git(args, d)
    out = []
    for line in (r.stdout or "").splitlines():
        parts = line.split("\t", 2)
        if len(parts) == 3:
            out.append({"hash": parts[0], "date": parts[1], "subject": parts[2]})
    return out


def revert_chapter(chapter: int) -> dict[str, Any]:
    """撤回某章：删该章正文 + 抽取增量文件 → 重新物化（记忆与正文一起干净回退）。"""
    d = repo_dir()
    removed = []
    for rel in (f"manuscript/ch{chapter}.zh.md", f"manuscript/ch{chapter}.en.md",
                f"memory/increments/ch{chapter}.json"):
        p = d / rel
        if p.exists():
            p.unlink(); removed.append(rel)
    commit(f"撤回 ch{chapter}")
    rep = materialize()
    return {"chapter": chapter, "removed": removed, "materialize": rep}


def create_branch(name: str) -> dict[str, Any]:
    """新建并切到分支（"如果这段剧情换个走向"的多结局并行探索）。"""
    d = repo_dir()
    r = _git(["checkout", "-b", name], d)
    return {"ok": r.returncode == 0, "branch": name, "out": (r.stdout + r.stderr)[-200:]}


def dump_suggestions(chapter: int, edits: list[dict[str, Any]]) -> dict[str, Any]:
    """把某章的润色建议(含锚点状态)落成 suggestions/ch<N>.json，随下次 commit 进 git（审计/可追溯）。"""
    sug = repo_dir() / "suggestions"
    sug.mkdir(parents=True, exist_ok=True)
    (sug / f"ch{chapter}.json").write_text(
        json.dumps({"chapter": chapter, "edits": edits}, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"chapter": chapter, "n": len(edits)}
