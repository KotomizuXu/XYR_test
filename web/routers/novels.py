"""REST API：小说列表、详情、章节内容、回滚。"""

import shutil
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from core.llm_client import LLMClient
from core.name_generator import sanitize_novel_name, suggest_novel_names
from core.pipeline import load_config
from core.state_manager import StateManager, ChapterState

router = APIRouter()


class SuggestNamesRequest(BaseModel):
    idea: str
    style: str | None = None


class ValidateNameRequest(BaseModel):
    name: str


@router.post("/suggest-names")
async def suggest_names(req: SuggestNamesRequest):
    config = load_config()
    llm = LLMClient(config)
    candidates = suggest_novel_names(llm, req.idea, style=req.style, n=3)
    return {"candidates": candidates}


@router.post("/validate-name")
async def validate_name(req: ValidateNameRequest):
    valid, msg = sanitize_novel_name(req.name)
    if valid:
        return {"valid": True}
    return {"valid": False, "error": msg}


@router.get("/novels")
async def list_novels():
    mgr = StateManager()
    names = mgr.list_novels()
    result = []
    for name in names:
        state = mgr.load(name)
        if not state:
            continue
        result.append({
            "name": name,
            "phase": state.phase,
            "current_chapter": min(state.current_chapter, state.total_chapters),
            "total_chapters": state.total_chapters,
            "story_idea_preview": (state.story_idea or "")[:200],
            "style_name": (state.style_guide or {}).get("style_name", ""),
            "created_at": state.created_at,
            "updated_at": state.updated_at,
            "chapters": [
                {
                    "number": ch.chapter_number,
                    "title": ch.title,
                    "stage": ch.stage,
                    "review_status": ch.review_status,
                    "revision_count": ch.revision_count,
                }
                for ch in state.chapters
            ],
        })
    return {"novels": result}


@router.get("/novels/{novel_name}")
async def get_novel_detail(novel_name: str):
    mgr = StateManager()
    state = mgr.load(novel_name)
    if not state:
        return {"error": "Novel not found"}
    return {
        "name": state.novel_name,
        "phase": state.phase,
        "story_idea": state.story_idea,
        "style_description": state.style_description,
        "style_guide": state.style_guide,
        "total_chapters": state.total_chapters,
        "current_chapter": state.current_chapter,
        "novel_params": state.novel_params,
        "world_data": state.world_data,
        "outline": state.outline,
        "chapters": [
            {
                "number": ch.chapter_number,
                "title": ch.title,
                "stage": ch.stage,
                "review_status": ch.review_status,
                "revision_count": ch.revision_count,
                "has_draft": ch.draft_path is not None,
                "has_edited": ch.edited_path is not None,
            }
            for ch in state.chapters
        ],
        "chapter_plans": state.chapter_plans,
        "refined_blocks": state.refined_blocks,
        "volumes": [
            {
                "number": v.number,
                "title": v.title,
                "start_chapter": v.start_chapter,
                "end_chapter": v.end_chapter,
            }
            for v in (state.volumes or [])
        ] if state.volumes else None,
        "capability_matrix": state.capability_matrix,
        "chapter_audits": state.chapter_audits,
        "batch_audits": state.batch_audits,
        "global_audit": state.global_audit,
    }


@router.get("/novels/{novel_name}/chapter/{chapter_num}")
async def get_chapter_content(novel_name: str, chapter_num: int):
    mgr = StateManager()
    state = mgr.load(novel_name)
    if not state:
        return {"error": "Novel not found"}
    for ch in state.chapters:
        if ch.chapter_number == chapter_num:
            path = Path(ch.edited_path) if ch.edited_path else (
                Path(ch.draft_path) if ch.draft_path else None
            )
            if path and path.exists():
                return {"content": path.read_text(encoding="utf-8")}
    return {"content": ""}


class RollbackRequest(BaseModel):
    target_phase: str


# Phase ordering for validation
_PHASE_ORDER = ["styling", "collecting_params", "directing", "plotting", "writing", "editing", "complete"]

# Subdirectories to clean on rollback
_CLEANUP_DIRS = ["tracking", "drafts", "edited", "final", "review_reports"]


@router.post("/novels/{novel_name}/rollback")
async def rollback_novel(novel_name: str, req: RollbackRequest):
    target = req.target_phase
    if target not in _PHASE_ORDER:
        return {"error": f"Invalid target phase: {target}"}

    mgr = StateManager()
    state = mgr.load(novel_name)
    if not state:
        return {"error": "Novel not found"}

    cur_idx = _PHASE_ORDER.index(state.phase) if state.phase in _PHASE_ORDER else 0
    tgt_idx = _PHASE_ORDER.index(target)
    if tgt_idx >= cur_idx:
        return {"error": "Cannot rollback to current or later phase"}

    novel_dir = mgr.get_novel_dir(novel_name)

    # --- Clean disk files ---
    if target in ("collecting_params", "directing"):
        for f in ("world.json", "outline.json", "chapters.json"):
            (novel_dir / f).unlink(missing_ok=True)
        for d in _CLEANUP_DIRS:
            _clean_dir(novel_dir / d)

    elif target == "plotting":
        (novel_dir / "chapters.json").unlink(missing_ok=True)
        for d in _CLEANUP_DIRS:
            _clean_dir(novel_dir / d)

    elif target == "writing":
        for d in _CLEANUP_DIRS:
            _clean_dir(novel_dir / d)

    # --- Clean state fields ---
    if target in ("collecting_params", "directing"):
        state.novel_params = None
        state.total_chapters = 0
        state.volumes = None
        state.world_data = None
        state.outline = None
        state.refined_blocks = []
        state.chapter_plans = None
        state.chapters = []
        state.current_chapter = 0

    elif target == "plotting":
        state.chapter_plans = None
        state.chapters = []
        state.current_chapter = 0

    elif target == "writing":
        state.chapters = [
            ChapterState(
                chapter_number=ch.chapter_number,
                title=ch.title,
                plot_points=ch.plot_points,
            )
            for ch in state.chapters
        ]
        state.current_chapter = 0

    state.phase = target
    mgr.save(state)
    return {"ok": True, "phase": target}


def _clean_dir(path: Path) -> None:
    """Remove all contents of a directory, then recreate it empty."""
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)
