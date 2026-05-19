"""State persistence for novel writing pipeline."""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent.parent / "output"


@dataclass
class ChapterState:
    chapter_number: int
    title: str = ""
    plot_points: str = ""
    draft_path: str | None = None
    review_status: str = "pending"  # pending | passed | needs_revision
    review_notes: str | None = None
    revision_count: int = 0
    edited_path: str | None = None
    final_path: str | None = None
    summary: str = ""


@dataclass
class NovelState:
    novel_name: str
    story_idea: str
    created_at: str = ""
    updated_at: str = ""
    phase: str = "styling"  # styling | directing | plotting | writing | reviewing | editing | complete
    current_chapter: int = 0
    world_data: dict | None = None
    outline: dict | None = None
    chapter_plans: list[dict] | None = None
    chapters: list[ChapterState] = field(default_factory=list)
    total_chapters: int = 0
    style_guide: dict | None = None
    style_description: str | None = None

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        self.updated_at = datetime.now().isoformat()


class StateManager:
    def get_novel_dir(self, novel_name: str) -> Path:
        return OUTPUT_DIR / novel_name

    def save(self, state: NovelState) -> Path:
        novel_dir = self.get_novel_dir(state.novel_name)
        novel_dir.mkdir(parents=True, exist_ok=True)
        state.updated_at = datetime.now().isoformat()

        state_path = novel_dir / "novel_state.json"
        tmp_path = novel_dir / "novel_state.json.tmp"

        data = asdict(state)
        tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(state_path)
        return state_path

    def load(self, novel_name: str) -> NovelState | None:
        state_path = self.get_novel_dir(novel_name) / "novel_state.json"
        if not state_path.exists():
            return None
        data = json.loads(state_path.read_text(encoding="utf-8"))
        chapters = [ChapterState(**ch) for ch in data.pop("chapters", [])]
        return NovelState(**data, chapters=chapters)

    def list_novels(self) -> list[str]:
        if not OUTPUT_DIR.exists():
            return []
        return [d.name for d in OUTPUT_DIR.iterdir() if d.is_dir() and (d / "novel_state.json").exists()]

    def ensure_dirs(self, novel_name: str) -> dict[str, Path]:
        """Create all output subdirectories and return path mapping."""
        base = self.get_novel_dir(novel_name)
        dirs = {
            "base": base,
            "drafts": base / "drafts",
            "edited": base / "edited",
            "final": base / "final",
            "reviews": base / "review_reports",
        }
        for d in dirs.values():
            d.mkdir(parents=True, exist_ok=True)
        return dirs
