"""Pipeline orchestrator: coordinates all agents."""

import json
import logging
import signal
import sys
from pathlib import Path

import yaml

from agents.director import DirectorAgent
from agents.editor import EditorAgent
from agents.plotter import PlotAgent
from agents.reviewer import ReviewerAgent
from agents.writer import WriterAgent
from core.context_manager import ContextManager
from core.llm_client import LLMClient
from core.state_manager import ChapterState, NovelState, StateManager

logger = logging.getLogger(__name__)


def load_config(config_path: str = None) -> dict:
    if config_path is None:
        config_path = Path(__file__).parent.parent / "config.yaml"
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


class NovelPipeline:
    def __init__(self, config_path: str = None):
        self.config = load_config(config_path)
        self.llm = LLMClient(self.config)
        self.state_mgr = StateManager()
        self.ctx_mgr = ContextManager(self.llm, self.config)

        self.director = DirectorAgent(self.llm, self.config)
        self.plotter = PlotAgent(self.llm, self.config)
        self.writer = WriterAgent(self.llm, self.config, self.ctx_mgr)
        self.reviewer = ReviewerAgent(self.llm, self.config)
        self.editor = EditorAgent(self.llm, self.config, self.ctx_mgr)

        self._interrupted = False
        signal.signal(signal.SIGINT, self._handle_interrupt)

    def _handle_interrupt(self, signum, frame):
        print("\n\n收到中断信号，正在保存进度...")
        self._interrupted = True

    def start_new_novel(self, story_idea: str, novel_name: str, num_chapters: int = None) -> None:
        if num_chapters is None:
            num_chapters = self.config["novel"]["default_chapters"]

        # Initialize state
        state = NovelState(
            novel_name=novel_name,
            story_idea=story_idea,
            phase="directing",
            total_chapters=num_chapters,
        )
        self.state_mgr.ensure_dirs(novel_name)
        self.state_mgr.save(state)

        print(f"\n{'='*60}")
        print(f"开始创作《{novel_name}》")
        print(f"故事灵感：{story_idea}")
        print(f"计划章节：{num_chapters}章")
        print(f"{'='*60}\n")

        try:
            self._run_pipeline(state)
        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            print(f"\n发生错误：{e}")
            print(f"进度已保存，可使用 'continue --name \"{novel_name}\"' 继续")
            raise

    def resume_novel(self, novel_name: str) -> None:
        state = self.state_mgr.load(novel_name)
        if state is None:
            print(f"未找到小说《{novel_name}》，请检查名称")
            return

        print(f"\n{'='*60}")
        print(f"继续创作《{novel_name}》")
        print(f"当前阶段：{state.phase}")
        print(f"当前章节：{state.current_chapter + 1}/{state.total_chapters}")
        print(f"{'='*60}\n")

        try:
            self._run_pipeline(state)
        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            print(f"\n发生错误：{e}")
            print(f"进度已保存，可使用 'continue --name \"{novel_name}\"' 继续")
            raise

    def _run_pipeline(self, state: NovelState) -> None:
        # Phase 1: Directing
        if state.phase == "directing":
            print("[导演] 正在构建世界观和大纲...")
            result = self.director.run(state.story_idea, state.total_chapters)
            state.world_data = result.get("world", {})
            state.outline = result.get("outline", {})
            # Save character data into world_data for reference
            if "characters" in result:
                state.world_data["characters"] = result["characters"]
            if "style" in result:
                state.outline["style"] = result["style"]

            # Save intermediate files
            novel_dir = self.state_mgr.get_novel_dir(state.novel_name)
            (novel_dir / "world.json").write_text(
                json.dumps(result.get("world", {}), ensure_ascii=False, indent=2), encoding="utf-8"
            )
            (novel_dir / "outline.json").write_text(
                json.dumps(result.get("outline", {}), ensure_ascii=False, indent=2), encoding="utf-8"
            )

            state.phase = "plotting"
            self.state_mgr.save(state)
            print("[导演] 世界观和大纲已完成\n")

        if self._interrupted:
            return

        # Phase 2: Plotting
        if state.phase == "plotting":
            print("[编剧] 正在拆分章节和规划剧情...")
            chapter_plans = self.plotter.run(state.outline, state.world_data, state.total_chapters)
            state.chapter_plans = chapter_plans

            novel_dir = self.state_mgr.get_novel_dir(state.novel_name)
            (novel_dir / "chapters.json").write_text(
                json.dumps(chapter_plans, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            # Initialize chapter states
            state.chapters = []
            for plan in chapter_plans:
                state.chapters.append(ChapterState(
                    chapter_number=plan.get("chapter_number", len(state.chapters) + 1),
                    title=plan.get("title", ""),
                    plot_points=json.dumps(plan.get("plot_points", []), ensure_ascii=False),
                ))

            state.phase = "writing"
            state.current_chapter = 0
            self.state_mgr.save(state)
            print(f"[编剧] {len(chapter_plans)} 章规划完成\n")

        if self._interrupted:
            return

        # Phase 3: Writing + Reviewing loop
        if state.phase in ("writing", "reviewing"):
            self._write_chapters(state)

        if self._interrupted:
            return

        # Phase 4: Editing
        if state.phase == "editing":
            self._edit_chapters(state)

        # Phase 5: Combine final output
        if state.phase == "editing" and state.current_chapter >= state.total_chapters:
            self._combine_final(state)
            state.phase = "complete"
            self.state_mgr.save(state)
            print(f"\n{'='*60}")
            print(f"《{state.novel_name}》创作完成！")
            print(f"输出目录：output/{state.novel_name}/final/")
            print(f"{'='*60}")

    def _write_chapters(self, state: NovelState) -> None:
        max_retries = self.config["novel"]["review_max_retries"]

        for i in range(state.current_chapter, state.total_chapters):
            if self._interrupted:
                return

            plan = state.chapter_plans[i]
            ch = state.chapters[i]
            ch_num = ch.chapter_number

            print(f"\n--- 第{ch_num}章：「{ch.title}」---")

            # Build running context
            completed_summaries = [c.summary for c in state.chapters[:i] if c.summary]
            running_ctx = self.ctx_mgr.build_running_context(
                state.world_data, state.outline, completed_summaries, plan
            )

            # Write draft
            print(f"  [作家] 正在撰写...")
            draft = self.writer.run(plan, running_ctx)

            # Save draft
            dirs = self.state_mgr.ensure_dirs(state.novel_name)
            draft_path = dirs["drafts"] / f"chapter_{ch_num:02d}.txt"
            draft_path.write_text(draft, encoding="utf-8")
            ch.draft_path = str(draft_path)

            # Review loop
            print(f"  [审核] 正在审稿...")
            review = self.reviewer.run(draft, plan, state.world_data)
            ch.review_notes = json.dumps(review, ensure_ascii=False)

            # Save review report
            review_path = dirs["reviews"] / f"chapter_{ch_num:02d}_review.json"
            review_path.write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")

            retries = 0
            while not review.get("approved", False) and retries < max_retries:
                retries += 1
                issues = review.get("issues", [])
                major = [i for i in issues if i.get("severity") == "major"]
                print(f"  [审核] 发现 {len(major)} 个主要问题，第{retries}次重写...")

                feedback = "\n".join(
                    f"- [{i.get('severity')}] {i.get('description')} → 建议：{i.get('suggestion')}"
                    for i in issues
                )
                draft = self.writer.rewrite(draft, feedback, plan, running_ctx)

                draft_path = dirs["drafts"] / f"chapter_{ch_num:02d}_r{retries}.txt"
                draft_path.write_text(draft, encoding="utf-8")
                ch.draft_path = str(draft_path)
                ch.revision_count = retries

                review = self.reviewer.run(draft, plan, state.world_data)
                ch.review_notes = json.dumps(review, ensure_ascii=False)

            if review.get("approved", False):
                ch.review_status = "passed"
                print(f"  [审核] 通过！质量评分：{review.get('overall_quality', '?')}/10")
            else:
                ch.review_status = "needs_revision"
                print(f"  [审核] 达到最大重试次数，接受当前版本")

            # Generate summary for context management
            summary = self.ctx_mgr.generate_chapter_summary(draft, ch_num)
            ch.summary = summary

            state.current_chapter = i + 1
            state.phase = "writing"
            self.state_mgr.save(state)

        # All chapters written, move to editing
        state.phase = "editing"
        state.current_chapter = 0
        self.state_mgr.save(state)
        print(f"\n全部 {state.total_chapters} 章撰写完成，进入编辑润色阶段\n")

    def _edit_chapters(self, state: NovelState) -> None:
        dirs = self.state_mgr.ensure_dirs(state.novel_name)

        for i in range(state.current_chapter, state.total_chapters):
            if self._interrupted:
                return

            ch = state.chapters[i]
            ch_num = ch.chapter_number
            print(f"  [编辑] 润色第{ch_num}章...")

            # Read the final draft (may have been revised)
            draft_path = Path(ch.draft_path) if ch.draft_path else dirs["drafts"] / f"chapter_{ch_num:02d}.txt"
            draft = draft_path.read_text(encoding="utf-8")

            # Get adjacent chapters for transition context
            prev_ending = ""
            next_opening = ""
            if i > 0:
                prev_ch = state.chapters[i - 1]
                if prev_ch.edited_path:
                    prev_text = Path(prev_ch.edited_path).read_text(encoding="utf-8")
                    prev_ending = prev_text
                elif prev_ch.draft_path:
                    prev_text = Path(prev_ch.draft_path).read_text(encoding="utf-8")
                    prev_ending = prev_text
            if i < state.total_chapters - 1:
                next_ch = state.chapters[i + 1]
                next_draft = dirs["drafts"] / f"chapter_{next_ch.chapter_number:02d}.txt"
                if next_draft.exists():
                    next_opening = next_draft.read_text(encoding="utf-8")

            edited = self.editor.run(draft, ch_num, prev_ending, next_opening)

            edited_path = dirs["edited"] / f"chapter_{ch_num:02d}.txt"
            edited_path.write_text(edited, encoding="utf-8")
            ch.edited_path = str(edited_path)

            state.current_chapter = i + 1
            self.state_mgr.save(state)

        print(f"  [编辑] 全部章节润色完成")

    def _combine_final(self, state: NovelState) -> None:
        dirs = self.state_mgr.ensure_dirs(state.novel_name)
        final_dir = dirs["final"]

        combined_parts = [f"《{state.novel_name}》\n\n"]

        for ch in state.chapters:
            ch_num = ch.chapter_number
            edited_path = Path(ch.edited_path) if ch.edited_path else None
            if not edited_path or not edited_path.exists():
                edited_path = Path(ch.draft_path) if ch.draft_path else None

            if not edited_path or not edited_path.exists():
                continue

            text = edited_path.read_text(encoding="utf-8")

            # Save individual final chapter
            final_path = final_dir / f"chapter_{ch_num:02d}.txt"
            final_path.write_text(text, encoding="utf-8")
            ch.final_path = str(final_path)

            # Add to combined
            combined_parts.append(f"第{ch_num}章 {ch.title}\n\n{text}\n\n")

        full_path = final_dir / f"{state.novel_name}_全文.txt"
        full_path.write_text("\n".join(combined_parts), encoding="utf-8")
        print(f"  全文已合并保存至：{full_path}")
