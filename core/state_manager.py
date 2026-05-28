"""State persistence for novel writing pipeline."""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent.parent / "output"


def atomic_write_json(path: Path, data) -> None:
    """通过 tmp+replace 原子写入 JSON 文件，避免写入中断导致文件损坏。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


@dataclass
class VolumeDef:
    number: int = 0
    title: str = ""
    start_chapter: int = 1
    end_chapter: int = 1


@dataclass
class ChapterState:
    chapter_number: int = 0
    title: str = ""
    plot_points: str = ""
    draft_path: str | None = None
    review_status: str = "pending"  # pending | passed | needs_revision
    review_notes: str | None = None
    revision_count: int = 0
    edited_path: str | None = None
    final_path: str | None = None
    summary: str = ""
    # 章内进度标记，用于 _write_chapters 中段中断后的精细恢复：
    #   pending → drafted（writer 完成）→ reviewed（审核循环结束）→ tracked（追踪更新完成）→ edited
    stage: str = "pending"


@dataclass
class NovelState:
    novel_name: str = ""
    story_idea: str = ""
    created_at: str = ""
    updated_at: str = ""
    phase: str = "styling"  # styling | collecting_params | directing | refining | plotting | writing | editing | complete
    current_chapter: int = 0
    world_data: dict | None = None
    outline: dict | None = None
    chapter_plans: list[dict] | None = None
    chapters: list[ChapterState] = field(default_factory=list)
    total_chapters: int = 0
    style_guide: dict | None = None
    style_description: str | None = None
    novel_params: dict | None = None
    # 精修阶段（Phase 1.5）已确认的 block 列表，断点续传时跳过；命名规则：
    #   "world" / "outline" / "character:<name>" / "location:<name>"
    refined_blocks: list[str] = field(default_factory=list)
    # 可选分卷结构，None 表示不分卷
    volumes: list[VolumeDef] | None = None
    # 卷级宏观摘要（Level 3 长程记忆）：{卷号(int): 摘要文本}。
    # Why: 300 章场景下，章节摘要必须再聚合为卷级，避免 running_context 线性膨胀。
    # 持久化到 state，避免每次续写都重新调用 LLM 重生成。
    volume_summaries: dict | None = None
    # 大纲审计数据（Plotting 阶段 Engine A→D 输出）
    capability_matrix: dict | None = None  # Engine A: 角色能力矩阵 + 世界规则 + 地点约束
    chapter_audits: list = field(default_factory=list)  # Engine B+C: 每章交叉校验结果
    batch_audits: list = field(default_factory=list)  # Engine D1+D2: 每批次遗忘/节奏审计
    global_audit: dict | None = None  # Engine D3+D4: 全局完整性 + 跨批次一致性

    def __post_init__(self):
        if not self.created_at:
            now = datetime.now().isoformat()
            self.created_at = now
            if not self.updated_at:
                self.updated_at = now


class StateManager:
    def get_novel_dir(self, novel_name: str) -> Path:
        return OUTPUT_DIR / novel_name

    def save(self, state: NovelState) -> Path:
        novel_dir = self.get_novel_dir(state.novel_name)
        novel_dir.mkdir(parents=True, exist_ok=True)
        state.updated_at = datetime.now().isoformat()

        state_path = novel_dir / "novel_state.json"
        atomic_write_json(state_path, asdict(state))
        return state_path

    def load(self, novel_name: str) -> NovelState | None:
        state_path = self.get_novel_dir(novel_name) / "novel_state.json"
        if not state_path.exists():
            return None
        data = json.loads(state_path.read_text(encoding="utf-8"))
        chapters = [ChapterState(**{k: v for k, v in ch.items() if k in ChapterState.__dataclass_fields__}) for ch in data.pop("chapters", [])]
        vol_data = data.pop("volumes", None)
        volumes = [VolumeDef(**v) for v in vol_data] if vol_data else None
        # JSON 不支持 int key，反序列化时还原 volume_summaries 的卷号为 int
        vs_raw = data.pop("volume_summaries", None)
        volume_summaries = {int(k): v for k, v in vs_raw.items()} if vs_raw else None
        valid = {k: v for k, v in data.items() if k in NovelState.__dataclass_fields__}
        return NovelState(**valid, chapters=chapters, volumes=volumes, volume_summaries=volume_summaries)

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
            "tracking": base / "tracking",
        }
        for d in dirs.values():
            d.mkdir(parents=True, exist_ok=True)
        return dirs
