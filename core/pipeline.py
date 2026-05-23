"""Pipeline orchestrator: coordinates all agents."""

import json
import logging
import signal
from pathlib import Path

import yaml

from agents.critic import CriticAgent
from agents.director import DirectorAgent
from agents.editor import EditorAgent
from agents.plotter import PlotAgent
from agents.reviewer import ReviewerAgent
from agents.style_advisor import StyleAdvisorAgent
from agents.writer import WriterAgent
from core.context_manager import ContextManager
from core.llm_client import LLMClient
from core.prompt_utils import (
    UserAbort, prompt_choice, prompt_int, prompt_multiline, prompt_single, prompt_yes_no,
)
from core.refine_prompts import (
    REFINE_WORLD_PROMPT, REFINE_CHARACTER_PROMPT,
    REFINE_LOCATION_PROMPT, REFINE_OUTLINE_PROMPT,
    REFINE_HOLISTIC_PROMPT,
    REFINE_REWRITE_DIRECTIVE,
)
from core.state_manager import ChapterState, NovelState, StateManager, atomic_write_json
from core.tracker import Tracker
from core import ui

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
        self.editor = EditorAgent(self.llm, self.config)
        self.style_advisor = StyleAdvisorAgent(self.llm, self.config)
        self.critic = CriticAgent(self.llm, self.config)

        self._interrupted = False
        self._current_state = None
        try:
            signal.signal(signal.SIGINT, self._handle_interrupt)
        except (ValueError, OSError):
            pass  # 非主线程无法注册信号处理器（Web 模式后台线程）

    def _apply_style_temperatures(self, style_guide: dict):
        if not style_guide or "agent_temperatures" not in style_guide:
            return
        agent_map = {
            "director": self.director,
            "plotter": self.plotter,
            "writer": self.writer,
            "reviewer": self.reviewer,
            "editor": self.editor,
            "style_advisor": self.style_advisor,
            "critic": self.critic,
        }
        for name, temp in style_guide["agent_temperatures"].items():
            if name in agent_map and isinstance(temp, (int, float)):
                agent_map[name].set_temperature(float(temp))

    def _apply_strictness(self, state: NovelState) -> None:
        genre = (state.style_guide or {}).get("setting", {}).get("genre", "")
        strictness = "strict"
        for keyword, level in self._GENRE_STRICTNESS.items():
            if keyword in genre:
                strictness = level
                break
        tracker = Tracker(self.state_mgr.get_novel_dir(state.novel_name), novel_name=state.novel_name)
        tracker.set_strictness(strictness)
        ui.info(f"[追踪系统] 审核严格度：{strictness}（题材：{genre or '未识别'}）")

    def _handle_interrupt(self, signum, frame):
        ui.warn("收到中断信号，正在保存进度...")
        self._interrupted = True
        if self._current_state:
            self.state_mgr.save(self._current_state)
            ui.success(f"进度已保存（阶段: {self._current_state.phase}）")
            ui.hint("使用 'python main.py continue' 恢复创作")

    def _checkpoint(self, state: NovelState, next_action: str) -> bool:
        """在重操作前保存状态并询问用户是否继续。返回 True 表示继续，False 表示暂停。"""
        self.state_mgr.save(state)
        # Web 模式：自动继续，不弹确认框（有断点续写兜底）
        try:
            from web.bridge.web_prompt import get_current_session
            if get_current_session() is not None:
                ui.info(f"下一步：{next_action}")
                return True
        except ImportError:
            pass
        ui.section("检查点", f"下一步：{next_action}", style="yellow")
        try:
            choice = prompt_choice(
                "请选择：",
                [("continue", "继续"), ("quit", "保存并退出")],
                default_key="continue",
            )
        except UserAbort:
            choice = "quit"
        if choice == "quit":
            self._interrupted = True
            return False
        return True

    def start_new_novel(self, story_idea: str, novel_name: str, style: str | None = None) -> None:
        # Initialize state
        state = NovelState(
            novel_name=novel_name,
            story_idea=story_idea,
            phase="styling",
            style_description=style,
        )
        self.state_mgr.ensure_dirs(novel_name)
        self.state_mgr.save(state)

        idea_preview = story_idea.replace("\n", " ")[:100]
        ui.banner(f"开始创作《{novel_name}》", idea_preview)

        try:
            self._run_pipeline(state)
        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            ui.error(f"发生错误：{e}")
            ui.hint("进度已保存，可使用 'continue' 继续")
            raise

    def resume_novel(self, novel_name: str) -> None:
        state = self.state_mgr.load(novel_name)
        if state is None:
            ui.error(f"未找到小说《{novel_name}》，请检查名称")
            return

        ui.banner(
            f"继续创作《{novel_name}》",
            f"阶段：{state.phase} · 进度：{state.current_chapter}/{state.total_chapters} 章",
        )

        self._apply_style_temperatures(state.style_guide)
        # 即使旧 state 已过 styling 阶段，也要重新应用 strictness（防止 styling 后 crash 导致 strictness 未生效）
        self._apply_strictness(state)

        try:
            self._run_pipeline(state)
        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            ui.error(f"发生错误：{e}")
            ui.hint("进度已保存，可使用 'continue' 继续")
            raise

    # 题材 → 审核严格度映射
    _GENRE_STRICTNESS = {
        "悬疑": "strict", "推理": "strict", "历史": "strict", "严肃": "strict", "科幻": "strict",
        "爽文": "flexible", "复仇": "flexible", "言情": "flexible", "甜文": "flexible",
        "虐文": "flexible", "网文": "flexible", "玄幻": "flexible", "仙侠": "flexible",
        "武侠": "flexible", "奇幻": "flexible", "都市": "flexible",
    }

    def _run_pipeline(self, state: NovelState) -> None:
        self._current_state = state

        # Phase 0: Styling
        if state.phase == "styling":
            ui.info(f"[风格顾问] 正在根据风格描述生成指南：{state.style_description or '传统文学风格，注重文笔和人物塑造'}")
            state.style_guide = self.style_advisor.run(state.style_description or "传统文学风格", story_idea=state.story_idea)
            self._apply_style_temperatures(state.style_guide)
            self._apply_strictness(state)
            state.phase = "collecting_params"
            self.state_mgr.save(state)
            ui.success(f"[风格顾问] 风格指南已生成：{state.style_guide.get('style_name', '?')}")

        if self._interrupted:
            return

        # Phase 0.5: Collect params
        if state.phase == "collecting_params":
            self._collect_params(state)

        if self._interrupted:
            return

        # Phase 1: Directing (一次性生成 + 全量精修)
        if state.phase == "directing":
            self._run_directing_holistic(state)

        if self._interrupted:
            return

        # Phase 2: Plotting
        if state.phase == "plotting":
            if not self._checkpoint(state, f"拆分 {state.total_chapters} 章剧情计划（耗时较长）"):
                return
            ui.info("[编剧] 正在拆分章节和规划剧情...")
            chapter_plans = self.plotter.run(state.outline, state.world_data, state.total_chapters, style_guide=state.style_guide, volumes=state.volumes)
            state.chapter_plans = chapter_plans

            novel_dir = self.state_mgr.get_novel_dir(state.novel_name)
            atomic_write_json(novel_dir / "chapters.json", chapter_plans)

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
            ui.success(f"[编剧] {len(chapter_plans)} 章规划完成")

        if self._interrupted:
            return

        # Phase 2.5: Initialize tracking system (ensure ALL tracking files exist)
        if state.phase == "writing":
            tracker = Tracker(self.state_mgr.get_novel_dir(state.novel_name), novel_name=state.novel_name)
            missing = [f for f in Tracker._TRACKING_FILES if not tracker._read_json(f)]
            config_missing = not tracker._read_json("config.json")
            if missing or config_missing:
                targets = list(missing) + (["config.json"] if config_missing else [])
                tracker.init_tracking(state.world_data, state.outline, state.chapter_plans, missing=targets)
            # 始终应用 active_validation_level（即使追踪文件已存在，也要根据 strictness 同步生效）
            self._apply_validation_level(tracker)

        if self._interrupted:
            return

        # Phase 3: Writing + Reviewing loop
        if state.phase == "writing":
            if not self._checkpoint(state, f"逐章写作 {state.total_chapters} 章（每章 3-5 分钟）"):
                return
            try:
                self._write_chapters(state)
            except Exception as e:
                logger.error(f"Writing phase error: {e}")
                state.phase = "writing"
                self.state_mgr.save(state)
                ui.error(f"写作阶段出错：{e}")
                ui.hint("进度已保存，可使用 'python main.py continue' 恢复")
                raise

        if self._interrupted:
            return

        # Phase 4: Editing
        if state.phase == "editing":
            if not self._checkpoint(state, f"逐章润色 {state.total_chapters} 章"):
                return
            try:
                self._edit_chapters(state)
            except Exception as e:
                logger.error(f"Editing phase error: {e}")
                state.phase = "editing"
                self.state_mgr.save(state)
                ui.error(f"编辑阶段出错：{e}")
                ui.hint("进度已保存，可使用 'python main.py continue' 恢复")
                raise

        # Phase 5: Combine final output
        if state.phase == "editing" and state.current_chapter >= state.total_chapters:
            self._combine_final(state)
            state.phase = "complete"
            self.state_mgr.save(state)
            from pathlib import Path
            ui.show_completion(state.novel_name, Path(f"output/{state.novel_name}/final/"))

    def _collect_params(self, state: NovelState) -> None:
        suggestions = (state.style_guide or {}).get("suggestions", {})
        cfg = self.config["novel"]

        # Defaults from config as fallback
        default_chapters = cfg["default_chapters"]
        default_min = cfg["words_per_chapter"]["min"]
        default_max = cfg["words_per_chapter"]["max"]

        # Style-based suggestions
        sug_chapters = suggestions.get("total_chapters", {})
        sug_words = suggestions.get("words_per_chapter", {})
        pace_desc = suggestions.get("pace_description", "")
        reward_desc = suggestions.get("reward_density", "")

        rec_chapters = sug_chapters.get("recommended", default_chapters)
        rec_min = sug_words.get("min", default_min)
        rec_max = sug_words.get("max", default_max)
        chapters_reason = sug_chapters.get("reason", "")
        words_reason = sug_words.get("reason", "")

        ui.show_param_suggestions(
            style_name=state.style_guide.get("style_name", "?"),
            rec_chapters=rec_chapters, rec_min=rec_min, rec_max=rec_max,
            chapters_reason=chapters_reason, words_reason=words_reason,
            pace_desc=pace_desc, reward_desc=reward_desc,
        )

        ui.section("请确认或调整以下参数", style="yellow")

        try:
            total_chapters = prompt_int(
                f"  总章数（直接回车使用建议值 {rec_chapters}）：", rec_chapters, min_val=1,
            )
            words_min = prompt_int(
                f"  每章最少字数（直接回车使用建议值 {rec_min}）：", rec_min, min_val=500,
            )
            words_max = prompt_int(
                f"  每章最多字数（直接回车使用建议值 {rec_max}）：", rec_max, min_val=words_min,
            )
        except UserAbort:
            self._interrupted = True
            ui.warn("已取消参数收集")
            return

        state.total_chapters = total_chapters
        state.novel_params = {
            "total_chapters": total_chapters,
            "words_per_chapter": {"min": words_min, "max": words_max},
        }

        # 可选分卷结构
        use_volumes = False
        if total_chapters >= 10:
            try:
                use_volumes = prompt_yes_no("  是否使用分卷结构？（长篇小说建议分卷）", default=False)
            except UserAbort:
                self._interrupted = True
                ui.warn("已取消参数收集")
                return
        if use_volumes:
            state.volumes = self._collect_volume_definitions(total_chapters, state.story_idea)
            state.novel_params["volumes"] = [
                {"number": v.number, "title": v.title, "start_chapter": v.start_chapter, "end_chapter": v.end_chapter}
                for v in state.volumes
            ]

        state.phase = "directing"
        self.state_mgr.save(state)

        # 遗忘检测阈值：直接采纳 AI 推荐值（不再让用户手动输入，体验过于宽泛）
        sug_thresholds = suggestions.get("tracking_thresholds", {})
        rec_char = sug_thresholds.get("character", max(3, total_chapters // 3))
        rec_plot = sug_thresholds.get("plotline", max(4, total_chapters * 2 // 5))
        rec_foreshadow = sug_thresholds.get("foreshadowing", max(5, total_chapters // 2))

        tracker = Tracker(self.state_mgr.get_novel_dir(state.novel_name), novel_name=state.novel_name)
        tracker.set_threshold("character", rec_char)
        tracker.set_threshold("plotline", rec_plot)
        tracker.set_threshold("foreshadowing", rec_foreshadow)

        ui.show_param_confirmed(
            total_chapters, words_min, words_max,
            {"character": rec_char, "plotline": rec_plot, "foreshadowing": rec_foreshadow},
        )

    def _collect_volume_definitions(self, total_chapters: int, story_idea: str) -> list:
        """通过 LLM 建议分卷方案，用户确认/调整后返回 VolumeDef 列表。"""
        from core.state_manager import VolumeDef
        ui.section("分卷规划", style="cyan")
        ui.info(f"共 {total_chapters} 章，正在生成分卷建议...")

        suggest_prompt = (
            f"故事灵感：{story_idea}\n\n"
            f"总章节数：{total_chapters}\n\n"
            f"请为这部小说设计分卷方案。每卷应有独立的叙事焦点和情感弧线。"
            f"卷的划分应基于故事的自然节奏（如地点转换、时间跳跃、阶段性的冲突与解决）。\n\n"
            f"输出 JSON 数组：[{{\"title\": \"卷名\", \"chapters\": \"起始章-结束章（如 1-8）\", \"reason\": \"分卷理由\"}}]\n"
            f"每卷建议 8-15 章。只输出 JSON，不要额外文字。"
        )
        result = self.llm.chat_json("你是一位小说结构规划师。", suggest_prompt, temperature=0.7)
        if not isinstance(result, list):
            ui.warn("分卷建议格式异常，跳过分卷")
            return None

        # 解析建议并展示
        suggestions = []
        ch_cursor = 1
        for i, item in enumerate(result, 1):
            title = item.get("title", f"卷{i}")
            chapters_str = item.get("chapters", "")
            reason = item.get("reason", "")
            try:
                parts = chapters_str.split("-")
                start = int(parts[0].strip())
                end = int(parts[1].strip())
            except (ValueError, IndexError):
                start = ch_cursor
                end = min(ch_cursor + total_chapters // len(result) - 1, total_chapters)
            suggestions.append({"number": i, "title": title, "start": start, "end": end, "reason": reason})
            ch_cursor = end + 1

        # 确保覆盖全部章节
        if suggestions:
            suggestions[-1]["end"] = max(suggestions[-1]["end"], total_chapters)

        ui.info("分卷建议：")
        for s in suggestions:
            ui.info(f"  卷{s['number']}「{s['title']}」：第{s['start']}-{s['end']}章 — {s['reason']}")

        try:
            accept = prompt_yes_no("  是否采纳此分卷方案？", default=True)
        except UserAbort:
            self._interrupted = True
            return None

        if not accept:
            ui.info("跳过分卷，将使用平面章节结构。")
            return None

        return [VolumeDef(s["number"], s["title"], s["start"], s["end"]) for s in suggestions]

    # ── Incremental Directing (Phase 1) ──────────────────────────────────

    # ── Holistic Directing (Phase 1) ───────────────────────────────────

    def _run_directing_holistic(self, state: NovelState) -> None:
        """Phase 1: 一次性生成世界观、角色、地点、大纲，全量精修确保一致性。"""
        ui.banner("导演阶段", "一次性构建世界观、角色、地点和大纲")

        # 兼容：增量流程断点恢复 — 剥离 planned 数据后走全量精修
        if state.world_data:
            state.world_data.pop("planned_cast", None)
            state.world_data.pop("planned_locations", None)

        # 已完成全量精修（断点续传）
        if "holistic" in state.refined_blocks:
            ui.hint("[恢复] 导演阶段已完成全量精修，跳过")
            self._advance_to_plotting(state)
            return

        # Step 1: 一次性生成（如果还没有数据）
        if not state.world_data:
            if not self._checkpoint(state, "一次性生成世界观、角色、地点和大纲（耗时较长）"):
                return
            ui.info("[导演] 正在一次生成全部设定...")
            result = self.director.run(
                state.story_idea, state.total_chapters, style_guide=state.style_guide, volumes=state.volumes)
            if not isinstance(result, dict) or not result:
                ui.error("[导演] 生成失败，请重试")
                return
            state.world_data = result
            state.outline = result.pop("outline", {})
            self.state_mgr.save(state)

        # Step 2: 全量精修
        full_json = self._merge_director_output(state)
        context = self._build_holistic_context(state)

        refined = self._refine_block(
            label="全部设定（世界观、角色、地点、大纲）",
            initial=full_json,
            system_prompt=REFINE_HOLISTIC_PROMPT,
            context_summary=context,
            on_update=lambda r: (
                self._split_director_output(state, r),
            ),
        )
        if self._interrupted:
            # 保存已调整数据但不推进 phase，恢复时可继续精修
            self._split_director_output(state, refined)
            ui.hint("[中断] 调整已保存，恢复后可继续精修")
            return

        # Step 3: 拆回 state
        self._split_director_output(state, refined)
        state.refined_blocks.append("holistic")
        self._advance_to_plotting(state)

    def _merge_director_output(self, state: NovelState) -> dict:
        """将 world_data + outline 合并为全量精修用的单一 JSON。"""
        wd = state.world_data or {}
        merged = {
            "world_data": {k: v for k, v in wd.items()
                           if k not in ("characters", "locations", "outline")},
            "characters": wd.get("characters", []),
            "locations": wd.get("locations", []),
            "outline": state.outline or {},
        }
        return merged

    # Expected top-level keys from director output (whitelist)
    _DIRECTOR_KEYS = {"world_data", "world", "characters", "locations", "outline", "style"}

    def _split_director_output(self, state: NovelState, merged: dict) -> None:
        """将全量精修结果拆回 state.world_data 和 state.outline。"""
        if not isinstance(merged, dict):
            return
        outline = merged.pop("outline", state.outline or {})
        characters = merged.pop("characters", state.world_data.get("characters", []))
        locations = merged.pop("locations", state.world_data.get("locations", []))
        merged.pop("style", None)  # legacy field, now handled by StyleAdvisor
        world_part = merged.get("world_data", merged)
        # 排除法：只过滤掉已知非 world_data 的顶层键，保留 LLM 生成的所有其他键
        _EXCLUDE_KEYS = {"world_data", "characters", "locations", "outline", "style"}
        if isinstance(world_part, dict):
            world_part = {k: v for k, v in world_part.items() if k not in _EXCLUDE_KEYS}
        state.world_data = {**world_part, "characters": characters, "locations": locations}
        state.outline = outline
        self.state_mgr.save(state)

    def _build_holistic_context(self, state: NovelState) -> str:
        """为全量精修构建上下文（故事火花 + 风格偏好）。"""
        parts: list[str] = []
        if state.story_idea:
            idea = state.story_idea.replace("\n", " ")
            parts.append(f"## 故事火花\n{idea[:1000]}")
        if state.style_description:
            parts.append(f"## 风格偏好\n{state.style_description}")
        return "\n\n".join(parts)

    def _advance_to_plotting(self, state: NovelState) -> None:
        """导演阶段收尾：持久化 JSON 文件，推进到 plotting。"""
        novel_dir = self.state_mgr.get_novel_dir(state.novel_name)
        wd = state.world_data or {}
        world_for_disk = {k: v for k, v in wd.items() if k not in ("characters", "locations")}
        world_for_disk["characters"] = wd.get("characters", [])
        world_for_disk["locations"] = wd.get("locations", [])
        atomic_write_json(novel_dir / "world.json", world_for_disk)
        atomic_write_json(novel_dir / "outline.json", state.outline)

        state.phase = "plotting"
        self.state_mgr.save(state)
        ui.success("[导演] 全部确认，进入剧情拆章")

    # ── Incremental Directing (Phase 1, 已弃用，保留兼容) ────────────────

    def _run_incremental_directing(self, state: NovelState) -> None:
        """Phase 1: 按层级增量生成世界观、角色、地点、大纲，每个 piece 生成后精修确认。"""
        ui.banner("导演阶段", "逐层构建世界观、角色、地点和大纲")

        # 向后兼容：如果 world_data 已有完整角色/地点但没有 planned_cast，
        # 说明是旧 state（旧 Director 一次性生成了全部），走旧精修流程
        if state.world_data and state.world_data.get("characters") and not state.world_data.get("planned_cast"):
            ui.hint("[兼容] 检测到旧版一次性生成数据，走精修流程")
            self._refine_director_output(state)
            return

        if not self._checkpoint(state, "构建世界观（耗时较长）"):
            return

        # --- Step 1: 生成+精修世界观 ---
        if "world" not in state.refined_blocks:
            if not state.world_data:
                ui.info("[导演] 正在生成世界观...")
                result = self.director.run_world(
                    state.story_idea, state.total_chapters, style_guide=state.style_guide)
                state.world_data = result
                self.state_mgr.save(state)

            wd = state.world_data or {}
            world_block = {k: v for k, v in wd.items()
                           if k not in ("characters", "locations")}
            context = self._build_incremental_context(state, exclude="world")
            refined = self._refine_block(
                label="世界观", initial=world_block,
                system_prompt=REFINE_WORLD_PROMPT, context_summary=context,
            )
            if self._interrupted:
                if isinstance(refined, dict):
                    state.world_data.update(refined)
                    self.state_mgr.save(state)
                return
            for k in list(state.world_data.keys()):
                if k not in ("characters", "locations", "planned_cast", "planned_locations"):
                    state.world_data.pop(k, None)
            if isinstance(refined, dict):
                state.world_data.update(refined)
            state.refined_blocks.append("world")
            self.state_mgr.save(state)

        if self._interrupted:
            return

        # --- Step 2: 逐个生成+精修角色 ---
        planned = list(state.world_data.get("planned_cast", []))
        if not planned and state.world_data.get("characters"):
            planned = [{"name": c.get("name"), "role": c.get("role"), "brief": ""}
                       for c in state.world_data["characters"] if isinstance(c, dict)]
        state.world_data.setdefault("characters", [])

        for idx, hint in enumerate(planned):
            if not isinstance(hint, dict):
                continue
            name = hint.get("name") or f"角色{idx + 1}"
            tag = f"character:{name}"
            if tag in state.refined_blocks:
                ui.hint(f"[恢复] 跳过角色「{name}」（已确认）")
                continue

            chars = state.world_data["characters"]
            while len(chars) <= idx:
                chars.append(None)

            if chars[idx] is None:
                ui.info(f"[导演] 正在生成角色「{name}」...")
                context_json = self._build_director_context_json(state)
                char_data = self.director.run_character(hint, context_json, state.style_guide)
                if not isinstance(char_data, dict) or not char_data:
                    ui.warn(f"角色「{name}」生成失败，跳过")
                    continue
                chars[idx] = char_data
                self.state_mgr.save(state)

            context = self._build_incremental_context(state)
            refined = self._refine_block(
                label=f"核心角色：{name}", initial=chars[idx],
                system_prompt=REFINE_CHARACTER_PROMPT, context_summary=context,
            )
            if self._interrupted:
                if isinstance(refined, dict):
                    state.world_data["characters"][idx] = refined
                    self.state_mgr.save(state)
                return
            if isinstance(refined, dict):
                state.world_data["characters"][idx] = refined
            state.refined_blocks.append(tag)
            self.state_mgr.save(state)

        if self._interrupted:
            return

        # --- Step 3: 逐个生成+精修地点 ---
        planned_locs = list(state.world_data.get("planned_locations", []))
        if not planned_locs and state.world_data.get("locations"):
            planned_locs = [{"name": l.get("name"), "type": l.get("type"), "brief": ""}
                           for l in state.world_data["locations"] if isinstance(l, dict)]
        state.world_data.setdefault("locations", [])

        for idx, hint in enumerate(planned_locs):
            if not isinstance(hint, dict):
                continue
            name = hint.get("name") or f"地点{idx + 1}"
            tag = f"location:{name}"
            if tag in state.refined_blocks:
                ui.hint(f"[恢复] 跳过地点「{name}」（已确认）")
                continue

            locs = state.world_data["locations"]
            while len(locs) <= idx:
                locs.append(None)

            if locs[idx] is None:
                ui.info(f"[导演] 正在生成地点「{name}」...")
                context_json = self._build_director_context_json(state)
                loc_data = self.director.run_location(hint, context_json, state.style_guide)
                if not isinstance(loc_data, dict) or not loc_data:
                    ui.warn(f"地点「{name}」生成失败，跳过")
                    continue
                locs[idx] = loc_data
                self.state_mgr.save(state)

            context = self._build_incremental_context(state)
            refined = self._refine_block(
                label=f"场景地点：{name}", initial=locs[idx],
                system_prompt=REFINE_LOCATION_PROMPT, context_summary=context,
            )
            if self._interrupted:
                if isinstance(refined, dict):
                    state.world_data["locations"][idx] = refined
                    self.state_mgr.save(state)
                return
            if isinstance(refined, dict):
                state.world_data["locations"][idx] = refined
            state.refined_blocks.append(tag)
            self.state_mgr.save(state)

        if self._interrupted:
            return

        # --- Step 4: 生成+精修大纲 ---
        if "outline" not in state.refined_blocks:
            if not state.outline:
                ui.info("[导演] 正在生成大纲...")
                context_json = self._build_director_context_json(state)
                outline_data = self.director.run_outline(
                    state.story_idea, state.total_chapters,
                    context_json, state.style_guide, volumes=state.volumes)
                state.outline = outline_data if isinstance(outline_data, dict) else {}
                self.state_mgr.save(state)

            context = self._build_incremental_context(state, exclude="outline")
            refined = self._refine_block(
                label="大纲（主题、三幕、关键转折）", initial=state.outline,
                system_prompt=REFINE_OUTLINE_PROMPT, context_summary=context,
            )
            if self._interrupted:
                if isinstance(refined, dict):
                    state.outline = refined
                    self.state_mgr.save(state)
                return
            if isinstance(refined, dict):
                state.outline = refined
            state.refined_blocks.append("outline")
            self.state_mgr.save(state)

        if self._interrupted:
            return

        # --- Step 5: 收尾 ---
        state.world_data.pop("planned_cast", None)
        state.world_data.pop("planned_locations", None)

        novel_dir = self.state_mgr.get_novel_dir(state.novel_name)
        world_for_disk = {k: v for k, v in state.world_data.items() if k not in ("characters", "locations")}
        world_for_disk["characters"] = state.world_data.get("characters", [])
        world_for_disk["locations"] = state.world_data.get("locations", [])
        atomic_write_json(novel_dir / "world.json", world_for_disk)
        atomic_write_json(novel_dir / "outline.json", state.outline)

        state.phase = "plotting"
        self.state_mgr.save(state)
        ui.success("[导演] 全部确认，进入剧情拆章")

    def _build_director_context_json(self, state: NovelState) -> str:
        """为 Director 增量生成构建完整已确认上下文的 JSON 字符串。"""
        parts = {}
        wd = state.world_data or {}
        world_part = {k: v for k, v in wd.items()
                      if k not in ("characters", "locations", "planned_cast", "planned_locations")}
        if world_part:
            parts["world"] = world_part
        confirmed_chars = [c for c in wd.get("characters", []) if isinstance(c, dict)]
        if confirmed_chars:
            parts["characters"] = confirmed_chars
        confirmed_locs = [l for l in wd.get("locations", []) if isinstance(l, dict)]
        if confirmed_locs:
            parts["locations"] = confirmed_locs
        return json.dumps(parts, ensure_ascii=False, indent=2)

    def _build_incremental_context(self, state: NovelState, exclude: str = "") -> str:
        """为增量精修构建上下文，包含所有已确认数据（不剥离角色/地点）。"""
        parts: list[str] = []
        if state.story_idea:
            idea = state.story_idea.replace("\n", " ")
            parts.append(f"## 故事火花\n{idea[:1000]}")
        if state.style_description:
            parts.append(f"## 风格偏好\n{state.style_description}")
        if exclude != "world" and state.world_data:
            wd = state.world_data
            brief = {k: v for k, v in wd.items()
                     if k not in ("characters", "locations", "planned_cast", "planned_locations")}
            if brief:
                parts.append(f"## 已确认世界观（参考，不必修改）\n{json.dumps(brief, ensure_ascii=False)[:4000]}")
        confirmed_chars = [c for c in (state.world_data or {}).get("characters", []) if isinstance(c, dict)]
        if confirmed_chars:
            parts.append(f"## 已确认角色（保持一致）\n{json.dumps(confirmed_chars, ensure_ascii=False)[:4000]}")
        confirmed_locs = [l for l in (state.world_data or {}).get("locations", []) if isinstance(l, dict)]
        if confirmed_locs:
            parts.append(f"## 已确认地点（保持一致）\n{json.dumps(confirmed_locs, ensure_ascii=False)[:3000]}")
        if exclude != "outline" and state.outline:
            parts.append(f"## 当前大纲（参考）\n{json.dumps(state.outline, ensure_ascii=False)[:3000]}")
        return "\n\n".join(parts)

    # ── Refining (Phase 1.5, 旧流程向后兼容) ────────────────────────────

    def _refine_director_output(self, state: NovelState) -> None:
        """Phase 1.5: 让用户分块打磨 Director 输出的世界观 / 角色卡 / 地点卡 / 大纲。

        每个 block 走 "是 / 调整 / 重写" 三选一循环（参考 braindump）。
        已确认的 block 名追加到 state.refined_blocks，断点续传时自动跳过。
        """
        ui.banner("精修阶段", "打磨 AI 生成的世界观、角色、地点和大纲")
        ui.hint("每个 block 都可以选择：确认 / 输入调整意见 / 整块重写")

        if state.refined_blocks:
            ui.hint(f"[恢复] 已确认 {len(state.refined_blocks)} 个 block：{state.refined_blocks}")

        self._refine_world(state)
        if self._interrupted:
            return

        self._refine_characters(state)
        if self._interrupted:
            return

        self._refine_locations(state)
        if self._interrupted:
            return

        self._refine_outline(state)
        if self._interrupted:
            return

        # 全部完成 → 持久化新版本，推进到 plotting
        novel_dir = self.state_mgr.get_novel_dir(state.novel_name)
        world_for_disk = {k: v for k, v in state.world_data.items() if k not in ("characters", "locations")}
        world_for_disk["characters"] = state.world_data.get("characters", [])
        world_for_disk["locations"] = state.world_data.get("locations", [])
        atomic_write_json(novel_dir / "world.json", world_for_disk)
        atomic_write_json(novel_dir / "outline.json", state.outline)

        state.phase = "plotting"
        self.state_mgr.save(state)
        ui.success("[精修] 全部确认，进入剧情拆章")

    def _build_refine_context(self, state: NovelState, exclude: str = "") -> str:
        """组装精修阶段共用的上下文（故事火花 + 风格 + 简要全局状态）。"""
        parts: list[str] = []
        if state.story_idea:
            idea = state.story_idea.replace("\n", " ")
            parts.append(f"## 故事火花\n{idea[:1000]}")
        if state.style_description:
            parts.append(f"## 风格偏好\n{state.style_description}")
        if exclude != "world":
            wd = state.world_data or {}
            brief = {k: v for k, v in wd.items() if k not in ("characters", "locations")}
            parts.append(f"## 当前世界观（参考，不必修改）\n{json.dumps(brief, ensure_ascii=False)[:2000]}")
        if exclude != "outline" and state.outline:
            parts.append(f"## 当前大纲（参考）\n{json.dumps(state.outline, ensure_ascii=False)[:1500]}")
        return "\n\n".join(parts)

    def _refine_world(self, state: NovelState) -> None:
        if "world" in state.refined_blocks:
            ui.hint("[恢复] 跳过世界观（已确认）")
            return
        wd = state.world_data or {}
        world_block = {k: v for k, v in wd.items() if k not in ("characters", "locations")}
        if not world_block:
            ui.hint("世界观为空，跳过精修")
            state.refined_blocks.append("world")
            self.state_mgr.save(state)
            return

        context = self._build_refine_context(state, exclude="world")
        refined = self._refine_block(
            label="世界观",
            initial=world_block,
            system_prompt=REFINE_WORLD_PROMPT,
            context_summary=context,
        )
        if self._interrupted:
            if isinstance(refined, dict):
                state.world_data.update(refined)
                self.state_mgr.save(state)
            return
        # 写回 state.world_data，保留 characters / locations
        for k in list(state.world_data.keys()):
            if k not in ("characters", "locations"):
                state.world_data.pop(k, None)
        if isinstance(refined, dict):
            state.world_data.update(refined)
        state.refined_blocks.append("world")
        self.state_mgr.save(state)

    def _refine_characters(self, state: NovelState) -> None:
        chars = (state.world_data or {}).get("characters", []) or []
        if not chars:
            ui.hint("无角色卡，跳过角色精修")
            return
        for idx, char in enumerate(chars):
            if not isinstance(char, dict):
                continue
            name = char.get("name") or f"角色{idx + 1}"
            tag = f"character:{name}"
            if tag in state.refined_blocks:
                ui.hint(f"[恢复] 跳过角色「{name}」（已确认）")
                continue
            context = self._build_refine_context(state, exclude="")
            # 注入"已确认的相邻角色"摘要
            sibling_names = [c.get("name", "?") for j, c in enumerate(chars) if j != idx and isinstance(c, dict)]
            if sibling_names:
                context += f"\n\n## 其他角色（保持设定一致）\n{', '.join(sibling_names)}"
            refined = self._refine_block(
                label=f"核心角色：{name}",
                initial=char,
                system_prompt=REFINE_CHARACTER_PROMPT,
                context_summary=context,
            )
            if self._interrupted:
                if isinstance(refined, dict):
                    state.world_data["characters"][idx] = refined
                    self.state_mgr.save(state)
                return
            if isinstance(refined, dict):
                state.world_data["characters"][idx] = refined
            state.refined_blocks.append(tag)
            self.state_mgr.save(state)

    def _refine_locations(self, state: NovelState) -> None:
        locs = (state.world_data or {}).get("locations", []) or []
        if not locs:
            ui.hint("无地点卡，跳过地点精修")
            return
        for idx, loc in enumerate(locs):
            if not isinstance(loc, dict):
                continue
            name = loc.get("name") or f"地点{idx + 1}"
            tag = f"location:{name}"
            if tag in state.refined_blocks:
                ui.hint(f"[恢复] 跳过地点「{name}」（已确认）")
                continue
            context = self._build_refine_context(state, exclude="")
            sibling_names = [l.get("name", "?") for j, l in enumerate(locs) if j != idx and isinstance(l, dict)]
            if sibling_names:
                context += f"\n\n## 其他地点（保持设定一致）\n{', '.join(sibling_names)}"
            refined = self._refine_block(
                label=f"场景地点：{name}",
                initial=loc,
                system_prompt=REFINE_LOCATION_PROMPT,
                context_summary=context,
            )
            if self._interrupted:
                if isinstance(refined, dict):
                    state.world_data["locations"][idx] = refined
                    self.state_mgr.save(state)
                return
            if isinstance(refined, dict):
                state.world_data["locations"][idx] = refined
            state.refined_blocks.append(tag)
            self.state_mgr.save(state)

    def _refine_outline(self, state: NovelState) -> None:
        if "outline" in state.refined_blocks:
            ui.hint("[恢复] 跳过大纲（已确认）")
            return
        if not state.outline:
            ui.hint("无大纲，跳过精修")
            state.refined_blocks.append("outline")
            self.state_mgr.save(state)
            return
        context = self._build_refine_context(state, exclude="outline")
        refined = self._refine_block(
            label="大纲（主题、三幕、关键转折）",
            initial=state.outline,
            system_prompt=REFINE_OUTLINE_PROMPT,
            context_summary=context,
        )
        if self._interrupted:
            if isinstance(refined, dict):
                state.outline = refined
                self.state_mgr.save(state)
            return
        if isinstance(refined, dict):
            state.outline = refined
        state.refined_blocks.append("outline")
        self.state_mgr.save(state)

    def _refine_block(self, *, label: str, initial, system_prompt: str, context_summary: str,
                      on_update=None):
        """通用打磨循环（"是/调整/重写"三选一），返回打磨后的内容。
        on_update(result): 每次调整后回调，用于将当前 result 写回 state 并保存到磁盘。
        """
        result = initial
        try:
            while True:
                ui.show_refine_block(label, result)

                # 内层：在当前 result 上反复调整，直到用户选 yes 或 rewrite
                inner_done = False
                while not inner_done:
                    if self._interrupted:
                        return result
                    action = self._confirm_refine(label)
                    if action == "yes":
                        return result
                    if action == "rewrite":
                        ui.info(f"重新生成「{label}」...")
                        inner_done = True  # 跳出内层 → 外层重生成
                        break
                    # adjust：用户给了反馈
                    ui.info(f"根据你的意见调整「{label}」：{action[:120]}{'...' if len(action) > 120 else ''}")
                    new_result = self._llm_refine(
                        system_prompt,
                        label=label,
                        current=result,
                        user_feedback=action,
                        context=context_summary,
                    )
                    if new_result is None:
                        ui.warn("打磨失败，保留当前版本")
                        continue
                    result = new_result
                    if on_update:
                        on_update(result)
                    ui.show_refine_block(label, result, modified=True)

                # 外层 rewrite 分支：整块重新生成（反上下文 + 升温 + 明示换思路）
                if self._interrupted:
                    return result
                new_result = self._llm_refine(
                    system_prompt,
                    label=label,
                    current=None,
                    user_feedback=None,
                    context=context_summary,
                    rewrite=True,
                    previous=result,
                )
                if new_result is None:
                    ui.warn("重生成失败，保留当前版本")
                    return result
                result = new_result
                if on_update:
                    on_update(result)
        except UserAbort:
            self._interrupted = True
            ui.warn("已取消打磨，保留当前版本")
            return result

    def _confirm_refine(self, label: str) -> str:
        """三选一：返回 'yes' / 'rewrite' / 用户自定义调整意见。"""
        choice = prompt_choice(
            f"  「{label}」如何处理？",
            [
                ("yes", "确认（继续下一块）"),
                ("adjust", "调整（告诉我哪里要改）"),
                ("rewrite", "重写（换方向整块重生成）"),
            ],
            default_key="yes",
        )
        if choice == "yes":
            return "yes"
        if choice == "rewrite":
            return "rewrite"
        feedback = prompt_multiline("  请说明要怎么调整：")
        return feedback if feedback else "yes"

    def _llm_refine(self, system_prompt: str, *, label: str,
                    current, user_feedback: str | None, context: str,
                    rewrite: bool = False, previous=None):
        """根据 user_feedback 调整 current；
        rewrite=True 时整块重生成（previous 作为反上下文，升温 0.9）。

        返回 dict / list（成功）或 None（解析失败）。
        """
        if rewrite:
            prev_json = json.dumps(previous, ensure_ascii=False, indent=2) if previous is not None else "(无)"
            user_msg = (
                f"## 上下文\n{context}\n\n"
                f"## 之前的版本（用户不满意，请勿沿用此方向）\n{prev_json}\n\n"
                f"## 任务\n请彻底换一种思路重新生成「{label}」，结构与之前版本一致（同字段、同嵌套），"
                f"但内容方向、风格、具体设定要明显不同，避免表面调整或同义替换。输出 JSON。"
            )
            sys_msg = system_prompt + REFINE_REWRITE_DIRECTIVE
            temperature = 0.9
        elif current is None:
            user_msg = (
                f"## 上下文\n{context}\n\n"
                f"## 任务\n请重新生成「{label}」的完整内容，输出 JSON。"
            )
            sys_msg = system_prompt
            temperature = 0.7
        else:
            user_msg = (
                f"## 上下文\n{context}\n\n"
                f"## 当前版本\n{json.dumps(current, ensure_ascii=False, indent=2)}\n\n"
                f"## 用户反馈\n{user_feedback}\n\n"
                f"请根据反馈调整「{label}」，输出完整修订后的 JSON（结构与当前版本一致）。"
            )
            sys_msg = system_prompt
            temperature = 0.7
        try:
            return self.llm.chat_json(sys_msg, user_msg, temperature=temperature)
        except Exception as e:
            logger.warning(f"_llm_refine failed for {label}: {e}")
            return None

    def _get_words_range(self, state: NovelState) -> tuple[int, int]:
        if state.novel_params and "words_per_chapter" in state.novel_params:
            wp = state.novel_params["words_per_chapter"]
            return wp["min"], wp["max"]
        cfg = self.config["novel"]["words_per_chapter"]
        return cfg["min"], cfg["max"]

    def _handle_retire(self, forgotten: dict, tracker: Tracker) -> None:
        """Allow user to retire forgotten elements they no longer want tracked."""
        all_items = []
        for char in forgotten.get("characters", []):
            all_items.append(("characters", char["name"], f"角色「{char['name']}」"))
        for plotline in forgotten.get("plotlines", []):
            all_items.append(("plotlines", plotline["name"], f"支线「{plotline['name']}」"))
        for fs in forgotten.get("foreshadowing", []):
            content = fs.get("content", "")[:30]
            all_items.append(("foreshadowing", fs.get("id", ""), f"伏笔「{content}...」"))

        if not all_items:
            return

        ui.hint("可选操作：输入编号退休（不再追踪）对应元素，直接回车跳过：")
        for idx, (_, _, desc) in enumerate(all_items, 1):
            ui.info(f"  {idx}. 退休 {desc}")
        try:
            choice = prompt_single("  > ")
        except UserAbort:
            return
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(all_items):
                etype, name, desc = all_items[idx]
                tracker.retire_element(etype, name)
                ui.success(f"已退休：{desc}")

    def _apply_validation_level(self, tracker: Tracker) -> None:
        """Set validation level based on strictness config."""
        strictness = tracker._get_strictness()
        level = "deep" if strictness == "strict" else "standard"
        rules = tracker._read_json("validation_rules.json")
        rules["active_validation_level"] = level
        tracker._write_json("validation_rules.json", rules)

    def _report_forgotten(self, forgotten: dict) -> None:
        ui.warn("[遗忘检测] 发现以下元素需要关注：")
        for char in forgotten.get("characters", []):
            ui.warn(f"  角色「{char['name']}」已{char['chapters_absent']}章未出场（上次：第{char['last_seen']}章）")
        for plotline in forgotten.get("plotlines", []):
            ui.warn(f"  支线「{plotline['name']}」停滞中（状态：{plotline.get('status', '?')}）")
        for fs in forgotten.get("foreshadowing", []):
            content = fs.get('content', '')
            ui.warn(f"  伏笔「{content[:60]}...」已{fs['chapters_since']}章未回收（埋设于第{fs['planted_chapter']}章）")

    def _build_forgotten_context(self, forgotten: dict) -> str:
        """Build context string from forgotten elements for writer awareness."""
        parts = ["## 遗忘元素提醒（写作时必须关注）"]
        if forgotten.get("characters"):
            parts.append("### 失踪角色（优先处理）")
            for char in forgotten["characters"]:
                parts.append(f"- {char['name']}（{char['role']}）已{char['chapters_absent']}章未出场，上次出现第{char['last_seen']}章，需要在本章提及或安排出场")
        if forgotten.get("plotlines"):
            parts.append("### 停滞支线（需要推进）")
            for plotline in forgotten["plotlines"]:
                parts.append(f"- 「{plotline['name']}」当前状态：{plotline.get('status', '?')}，需要在本章推进")
        if forgotten.get("foreshadowing"):
            parts.append("### 未回收伏笔（考虑回收或提醒）")
            for fs in forgotten["foreshadowing"]:
                parts.append(f"- [{fs.get('id', '')}] {fs.get('content', '')[:50]}，埋设于第{fs['planted_chapter']}章，已{fs['chapters_since']}章未回收")
        return "\n".join(parts)

    def _pre_write_check(self, state: NovelState, tracker: Tracker) -> None:
        checks = {
            "style_guide": state.style_guide is not None,
            "world_data": bool(state.world_data),
            "outline": bool(state.outline),
            "chapter_plans": bool(state.chapter_plans),
            "character_state": bool(tracker._read_json("character_state.json")),
            "plot_tracker": bool(tracker._read_json("plot_tracker.json")),
            "relationships": bool(tracker._read_json("relationships.json")),
            "validation_rules": bool(tracker._read_json("validation_rules.json")),
        }
        missing = [k for k, v in checks.items() if not v]
        if missing:
            ui.warn(f"[写前检查] 缺失数据：{missing}，继续写作但可能影响一致性")

        # Report validation level
        if checks["validation_rules"]:
            strictness = tracker._get_strictness()
            ui.hint(f"[写前检查] 验证模式：{strictness}")

        # Extract key principle summaries for writer context
        if checks["style_guide"] and state.style_guide:
            style_name = state.style_guide.get("style_name", "")
            tone = state.style_guide.get("tone", {}).get("overall", "")
            if style_name:
                ui.hint(f"[写前检查] 风格：{style_name}")
            reqs = state.style_guide.get("requirements", {}).get("detected", [])
            if reqs:
                ui.hint(f"[写前检查] 写作规范：{', '.join(reqs)}")
            dealbreakers = state.style_guide.get("review", {}).get("dealbreakers", [])
            if dealbreakers:
                ui.warn(f"[写前检查] 红线：{', '.join(str(d) for d in dealbreakers[:5])}")
            style_rules = state.style_guide.get("style_presets", {}).get("style_rules", [])
            if style_rules:
                ui.hint(f"[写前检查] 文风要点：{'; '.join(str(r) for r in style_rules[:5])}")

        # Extract key character states
        char_state = tracker._read_json("character_state.json")
        if char_state:
            protag = char_state.get("protagonist", {})
            if protag.get("name"):
                phase = protag.get("development", {}).get("currentPhase", "")
                loc = protag.get("currentStatus", {}).get("location", "")
                ui.hint(f"[写前检查] 主角{protag['name']}：阶段={phase}，位置={loc or '未知'}")

    def _write_chapters(self, state: NovelState) -> None:
        # I2: review-rewrite 循环硬上限。即便审稿一直 reject，也最多重写 max_retries 次后接受当前版本
        max_retries = self.config["novel"]["review_max_retries"]
        words_min, words_max = self._get_words_range(state)
        tracker = Tracker(self.state_mgr.get_novel_dir(state.novel_name), novel_name=state.novel_name)

        for i in range(state.current_chapter, state.total_chapters):
            if self._interrupted:
                return

            plan = state.chapter_plans[i]
            ch = state.chapters[i]
            ch_num = ch.chapter_number

            ui.section(
                f"第 {ch_num}/{state.total_chapters} 章 · 「{ch.title}」",
                body=f"进度：{i}/{state.total_chapters} 章已完成",
                style="bright_cyan",
            )

            # Pre-write checklist
            self._pre_write_check(state, tracker)

            # Pre-write checklist: build full context with tracking data
            tracking_ctx = tracker.get_tracking_context(ch_num)

            # Check forgotten elements
            forgotten = tracker.check_forgotten(ch_num)
            if forgotten:
                self._report_forgotten(forgotten)
                # Allow user to retire forgotten elements
                self._handle_retire(forgotten, tracker)
                # Inject forgotten elements into tracking context for writer awareness
                forgotten_ctx = self._build_forgotten_context(forgotten)
                if forgotten_ctx:
                    tracking_ctx = f"{tracking_ctx}\n\n{forgotten_ctx}" if tracking_ctx else forgotten_ctx

            # Build running context
            completed_summaries = [c.summary for c in state.chapters[:i] if c.summary]
            running_ctx = self.ctx_mgr.build_running_context(
                state.world_data, state.outline, completed_summaries, plan,
                tracking_context=tracking_ctx, story_idea=state.story_idea,
                volumes=state.volumes,
            )

            # ──────────── Stage 1: Writer draft（可跳过：已有 drafted 标记 + 文件存在）────────────
            dirs = self.state_mgr.ensure_dirs(state.novel_name)
            draft_path = dirs["drafts"] / f"chapter_{ch_num:02d}.txt"

            if ch.stage in ("drafted", "reviewed", "tracked") and ch.draft_path and Path(ch.draft_path).exists():
                draft = Path(ch.draft_path).read_text(encoding="utf-8")
                ui.hint(f"[恢复] 跳过 writer，复用已存在草稿（stage={ch.stage}）")
            else:
                ui.info("[作家] 正在撰写...")
                draft = self.writer.run(plan, running_ctx, style_guide=state.style_guide, words_min=words_min, words_max=words_max)
                draft_path.write_text(draft, encoding="utf-8")
                ch.draft_path = str(draft_path)
                ch.stage = "drafted"
                self.state_mgr.save(state)

                # Programmatic checks: character name alias fix
                fixed = False
                fix_result = tracker.auto_fix(draft, ch_num)
                if fix_result["fixes"]["applied"]:
                    draft = fix_result["text"]
                    fixed = True
                    ui.hint(f"[追踪] 自动修正角色名：{fix_result['fixes']['applied']}")

                # Programmatic checks: banned AI words auto-fix
                fixed_draft, banned_changes = tracker.auto_fix_banned_words(draft, state.style_guide)
                if banned_changes:
                    draft = fixed_draft
                    fixed = True
                    ui.hint(f"[禁用词] 自动修正 {len(banned_changes)} 处：{banned_changes[:5]}")

                # Programmatic checks: cliché/sentence/abstract patterns (report only)
                cliche_issues = tracker.check_cliches(draft)
                if cliche_issues:
                    ui.warn(f"[陈词滥调] 发现 {len(cliche_issues)} 处：{cliche_issues[:3]}")

                sentence_issues = tracker.check_sentence_patterns(draft)
                if sentence_issues:
                    ui.hint(f"[句式检查] {sentence_issues[:3]}")

                abstract_issues = tracker.check_abstract_nouns(draft)
                if abstract_issues:
                    ui.hint(f"[抽象名词] 发现 {len(abstract_issues)} 处：{abstract_issues[:5]}")

                if fixed:
                    draft_path.write_text(draft, encoding="utf-8")

            # ──────────── Stage 2: Review loop（可跳过：已有 reviewed 标记）────────────
            if ch.stage in ("reviewed", "tracked") and ch.review_notes:
                review = json.loads(ch.review_notes)
                ui.hint(f"[恢复] 跳过审核，复用已存在 review_notes（stage={ch.stage}）")
            else:
                # Review with tracking context for consistency checking
                ui.info("[审核] 正在审稿（含一致性校验）...")
                review = self.reviewer.run(draft, plan, state.world_data, style_guide=state.style_guide, tracking_context=tracking_ctx)
                ch.review_notes = json.dumps(review, ensure_ascii=False)

                # Save review report
                review_path = dirs["reviews"] / f"chapter_{ch_num:02d}_review.json"
                atomic_write_json(review_path, review)

            retries = 0
            while not review.get("approved", False) and retries < max_retries:
                retries += 1
                issues = review.get("issues", [])
                if not issues:
                    logger.warning(f"Review not approved but no issues listed, accepting as-is")
                    break
                major = [i for i in issues if i.get("severity") == "major"]
                ui.warn(f"[审核] 发现 {len(major)} 个主要问题，第{retries}次重写...")

                feedback = "\n".join(
                    f"- [{i.get('severity')}] {i.get('description')} → 建议：{i.get('suggestion')}"
                    for i in issues
                )
                strengths = review.get("strengths", [])
                if strengths:
                    feedback += "\n\n以下部分写得很好，重写时请保留：\n" + "\n".join(
                        f"- {s}" for s in strengths
                    )
                draft = self.writer.rewrite(draft, feedback, plan, running_ctx, style_guide=state.style_guide, words_min=words_min, words_max=words_max)

                draft_path = dirs["drafts"] / f"chapter_{ch_num:02d}_r{retries}.txt"
                draft_path.write_text(draft, encoding="utf-8")
                ch.draft_path = str(draft_path)
                ch.revision_count = retries

                review = self.reviewer.run(draft, plan, state.world_data, style_guide=state.style_guide, tracking_context=tracking_ctx)
                ch.review_notes = json.dumps(review, ensure_ascii=False)

            if review.get("approved", False):
                ch.review_status = "passed"
                # Calculate and override consistency score using tracker formula
                calc_score = tracker.calculate_consistency_score(review)
                review["consistency_score"] = calc_score
                ui.success(f"[审核] 通过！质量评分：{review.get('overall_quality', '?')}/10，一致性：{calc_score}%")
                # 展示八维质量评分（quality_breakdown 消费）
                breakdown = review.get("quality_breakdown", {})
                if breakdown:
                    dim_names = {
                        "opening_hook": "开头", "plot_progression": "剧情", "character_depth": "人物",
                        "dialogue_quality": "对话", "ending_hook": "结尾", "pacing": "节奏",
                        "show_not_tell": "展示", "language_quality": "语言",
                    }
                    dims = []
                    for dim, label in dim_names.items():
                        s = breakdown.get(dim)
                        if s is not None:
                            dims.append(f"{label}={s}")
                    total = breakdown.get("total")
                    if total is not None:
                        dims.append(f"总分={total}/80")
                    if dims:
                        ui.hint(f"[质量分维] {', '.join(dims)}")
                consistency = review.get("consistency_checks", {})
                if consistency:
                    for key in ("character_issues", "world_issues", "timeline_issues",
                                "physical_traits_issues", "personality_issues", "knowledge_state_issues"):
                        issues = consistency.get(key, [])
                        if issues:
                            ui.warn(f"[一致性] {key}：{issues}")
                # Apply auto_fix_suggestions from reviewer
                auto_fixes = review.get("auto_fix_suggestions", [])
                if auto_fixes:
                    applied = []
                    for fix in auto_fixes:
                        if fix.get("confidence", 0) >= 0.9 and fix.get("original") and fix.get("suggested"):
                            draft = draft.replace(fix["original"], fix["suggested"], 1)
                            applied.append(f"'{fix['original']}' → '{fix['suggested']}'")
                    if applied:
                        draft_path.write_text(draft, encoding="utf-8")
                        ui.hint(f"[自动修复] 审核建议修复 {len(applied)} 处：{applied[:3]}")
            else:
                ch.review_status = "needs_revision"
                ui.warn(f"[审核] 已达 review_max_retries={max_retries} 上限（I2 硬上限），接受当前版本进入下一阶段")

            # Mark stage=reviewed before tracking update（中断恢复时跳过审核循环）
            if ch.stage != "tracked":
                ch.stage = "reviewed"
                self.state_mgr.save(state)

            # ──────────── Stage 3: Tracking update（可跳过：已有 tracked 标记）────────────
            if ch.stage != "tracked":
                # Generate summary for context management
                summary = self.ctx_mgr.generate_chapter_summary(draft, ch_num)
                ch.summary = summary

                # Update tracking data (pass review for L1.1 consumption)
                before = tracker.snapshot()
                tracker.update_tracking(ch_num, draft, plan, review=review)
                # L2: Extract tracking_updates from reviewer output
                if review.get("tracking_updates"):
                    tracker.update_from_review(ch_num, review)

                # L3: Independent LLM analysis every 5 chapters
                if ch_num % 5 == 0 and ch_num < state.total_chapters:
                    ui.info("[追踪] 正在分析角色成长弧线...")
                    completed_summaries = [c.summary for c in state.chapters[:i + 1] if c.summary]
                    tracker.analyze_development(self.llm, completed_summaries, state.total_chapters, ch_num)

                after = tracker.snapshot()
                tracker.log_changes_csv(ch_num, before, after)

                ch.stage = "tracked"
                # Volume boundary check
                if state.volumes:
                    tracker.advance_volume(ch_num, state.volumes)
                self.state_mgr.save(state)
            else:
                ui.hint(f"[恢复] 跳过追踪更新，复用已存在数据（stage=tracked）")

            state.current_chapter = i + 1
            state.phase = "writing"
            self.state_mgr.save(state)

        # All chapters written, move to editing
        state.phase = "editing"
        state.current_chapter = 0
        self.state_mgr.save(state)
        ui.success(f"全部 {state.total_chapters} 章撰写完成，进入编辑润色阶段")

    def _edit_chapters(self, state: NovelState) -> None:
        dirs = self.state_mgr.ensure_dirs(state.novel_name)
        tracker = Tracker(self.state_mgr.get_novel_dir(state.novel_name), novel_name=state.novel_name)

        for i in range(state.current_chapter, state.total_chapters):
            if self._interrupted:
                return

            ch = state.chapters[i]
            ch_num = ch.chapter_number
            ui.info(f"[编辑] 润色第 {ch_num}/{state.total_chapters} 章...")

            # Read the final draft (may have been revised)
            draft_path = Path(ch.draft_path) if ch.draft_path else dirs["drafts"] / f"chapter_{ch_num:02d}.txt"
            draft = draft_path.read_text(encoding="utf-8")

            # Get tracking context for consistency during editing
            tracking_ctx = tracker.get_tracking_context(ch_num)

            # Get adjacent chapters for transition context
            prev_ending, next_opening = self._get_adjacent_text(state, ch_num)

            edited = self.editor.run(draft, ch_num, prev_ending, next_opening, style_guide=state.style_guide, tracking_context=tracking_ctx)

            edited_path = dirs["edited"] / f"chapter_{ch_num:02d}.txt"
            edited_path.write_text(edited, encoding="utf-8")
            ch.edited_path = str(edited_path)

            state.current_chapter = i + 1
            self.state_mgr.save(state)

        ui.success("[编辑] 全部章节润色完成")

    def _combine_final(self, state: NovelState) -> None:
        dirs = self.state_mgr.ensure_dirs(state.novel_name)
        final_dir = dirs["final"]

        combined_parts = [f"《{state.novel_name}》\n\n"]

        if state.volumes:
            for vol in state.volumes:
                vol_parts = [f"══════════════════════════════\n"
                             f"卷{vol.number}  {vol.title}\n"
                             f"（第{vol.start_chapter}章 — 第{vol.end_chapter}章）\n"
                             f"══════════════════════════════\n\n"]
                for ch in state.chapters[vol.start_chapter - 1 : vol.end_chapter]:
                    ch_num = ch.chapter_number
                    text = self._read_chapter_text(ch)
                    if text is None:
                        continue
                    final_path = final_dir / f"chapter_{ch_num:02d}.txt"
                    final_path.write_text(text, encoding="utf-8")
                    ch.final_path = str(final_path)
                    header = f"第{ch_num}章 {ch.title}\n\n"
                    combined_parts.append(header + text + "\n\n")
                    vol_parts.append(header + text + "\n\n")
                vol_path = final_dir / f"{state.novel_name}_卷{vol.number}.txt"
                vol_path.write_text("".join(vol_parts), encoding="utf-8")
        else:
            for ch in state.chapters:
                ch_num = ch.chapter_number
                text = self._read_chapter_text(ch)
                if text is None:
                    continue
                final_path = final_dir / f"chapter_{ch_num:02d}.txt"
                final_path.write_text(text, encoding="utf-8")
                ch.final_path = str(final_path)
                combined_parts.append(f"第{ch_num}章 {ch.title}\n\n{text}\n\n")

        full_path = final_dir / f"{state.novel_name}_全文.txt"
        full_path.write_text("".join(combined_parts), encoding="utf-8")
        ui.success(f"全文已合并保存至：{full_path}")

    @staticmethod
    def _read_chapter_text(ch) -> str | None:
        edited_path = Path(ch.edited_path) if ch.edited_path else None
        if not edited_path or not edited_path.exists():
            edited_path = Path(ch.draft_path) if ch.draft_path else None
        if not edited_path or not edited_path.exists():
            return None
        return edited_path.read_text(encoding="utf-8")

    # ── Revise flow ──────────────────────────────────────────────

    def revise_chapter(self, novel_name: str, chapter_number: int) -> None:
        state = self.state_mgr.load(novel_name)
        if state is None:
            ui.error(f"未找到小说《{novel_name}》，请检查名称")
            return

        if state.phase not in ("editing", "complete"):
            ui.error(f"小说《{novel_name}》尚未完成主写作流程（当前阶段：{state.phase}），请先用 'continue' 完成创作再修订")
            return

        ch = self._find_chapter(state, chapter_number)
        if ch is None:
            ui.error(f"第{chapter_number}章不存在")
            return

        draft_path = Path(ch.edited_path) if ch.edited_path else (Path(ch.draft_path) if ch.draft_path else None)
        if not draft_path or not draft_path.exists():
            ui.error(f"第{chapter_number}章尚未完成，无法修订")
            return

        draft = draft_path.read_text(encoding="utf-8")

        ui.section(f"修订第{chapter_number}章", f"「{ch.title}」· 当前版本 {len(draft)} 字", style="bright_cyan")

        try:
            user_feedback = self._collect_user_feedback()
        except (KeyboardInterrupt, EOFError):
            ui.hint("已取消输入，退出修订")
            return

        if not user_feedback:
            ui.hint("未输入修改意见，退出修订")
            return

        self._apply_style_temperatures(state.style_guide)

        try:
            tracker = Tracker(self.state_mgr.get_novel_dir(novel_name), novel_name=novel_name)
            tracking_ctx = tracker.get_tracking_context(chapter_number)

            idx = chapter_number - 1
            chapter_plan = state.chapter_plans[idx] if state.chapter_plans and 0 <= idx < len(state.chapter_plans) else {}

            ui.info("[修订顾问] 正在分析修改意见...")
            ideas = self.critic.run(
                chapter_text=draft,
                user_feedback=user_feedback,
                chapter_plan=chapter_plan,
                world_data=state.world_data,
                tracking_context=tracking_ctx,
                style_guide=state.style_guide,
            )

            if self._interrupted:
                return

            try:
                selected = self._select_idea(ideas, user_feedback)
            except (KeyboardInterrupt, EOFError):
                ui.hint("已取消选择，退出修订")
                return

            self._execute_revise(state, ch, draft, selected, user_feedback, chapter_plan, tracking_ctx, tracker)
        except Exception as e:
            logger.error(f"Revise error: {e}")
            ui.error(f"修订出错：{e}")
            raise

    def _execute_revise(self, state, ch, draft, selected_idea, user_feedback, chapter_plan, tracking_ctx, tracker):
        ch_num = ch.chapter_number
        words_min, words_max = self._get_words_range(state)

        i = ch_num - 1
        completed_summaries = [c.summary for c in state.chapters[:i] if c.summary]
        running_ctx = self.ctx_mgr.build_running_context(
            state.world_data, state.outline, completed_summaries, chapter_plan,
            tracking_context=tracking_ctx, story_idea=state.story_idea,
            volumes=state.volumes,
        )

        if isinstance(selected_idea, dict):
            feedback = (
                f"## 修改方向：{selected_idea.get('title', '')}\n"
                f"{selected_idea.get('description', '')}\n"
                f"修改范围：{selected_idea.get('scope', '')}\n"
                f"预期效果：{selected_idea.get('expected_effect', '')}\n\n"
                f"用户原始意见：{user_feedback}"
            )
        else:
            feedback = f"## 修改要求\n{selected_idea}"

        # Step 1: Writer rewrite
        ui.info("[作家] 正在根据修改思路修订...")
        revised = self.writer.rewrite(
            draft, feedback, chapter_plan, running_ctx,
            style_guide=state.style_guide,
            words_min=words_min, words_max=words_max,
        )

        if self._interrupted:
            ui.hint("已中断，修订未保存")
            return

        # Step 2: Review
        ui.info("[审核] 正在审核修订版本...")
        review = self.reviewer.run(
            revised, chapter_plan, state.world_data,
            style_guide=state.style_guide,
            tracking_context=tracking_ctx,
        )

        if self._interrupted:
            ui.hint("已中断，修订未保存")
            return

        # Step 3: Retry once if major issues
        if not review.get("approved", False):
            major = [iss for iss in review.get("issues", []) if iss.get("severity") == "major"]
            if major:
                ui.warn(f"[审核] 发现 {len(major)} 个主要问题，再次修订...")
                additional = "\n".join(
                    f"- [{iss.get('severity')}] {iss.get('description')} → {iss.get('suggestion')}"
                    for iss in review.get("issues", [])
                )
                strengths = review.get("strengths", [])
                if strengths:
                    additional += "\n\n以下部分写得很好，重写时请保留：\n" + "\n".join(
                        f"- {s}" for s in strengths
                    )
                revised = self.writer.rewrite(
                    revised, additional, chapter_plan, running_ctx,
                    style_guide=state.style_guide,
                    words_min=words_min, words_max=words_max,
                )
                review = self.reviewer.run(
                    revised, chapter_plan, state.world_data,
                    style_guide=state.style_guide,
                    tracking_context=tracking_ctx,
                )

        if self._interrupted:
            ui.hint("已中断，修订未保存")
            return

        # Step 4: Editor polish
        ui.info("[编辑] 正在润色修订版本...")
        prev_ending, next_opening = self._get_adjacent_text(state, ch_num)
        final_text = self.editor.run(
            revised, ch_num, prev_ending, next_opening,
            style_guide=state.style_guide,
            tracking_context=tracking_ctx,
        )

        # Step 5: User confirmation
        ui.success(f"修订完成，字数变化：{len(draft)} → {len(final_text)}")
        try:
            accept = prompt_yes_no("是否接受此次修订？", default=True)
        except UserAbort:
            ui.hint("已中断，修订未保存")
            return

        if not accept:
            ui.hint("已放弃修订，保留原版本")
            return

        # Programmatic fixes on revised text
        fixed = False
        fix_result = tracker.auto_fix(final_text, ch_num)
        if fix_result["fixes"]["applied"]:
            final_text = fix_result["text"]
            fixed = True
            ui.hint(f"[追踪] 自动修正角色名：{fix_result['fixes']['applied']}")

        fixed_draft, banned_changes = tracker.auto_fix_banned_words(final_text, state.style_guide)
        if banned_changes:
            final_text = fixed_draft
            fixed = True
            ui.hint(f"[禁用词] 自动修正 {len(banned_changes)} 处：{banned_changes[:5]}")

        cliche_issues = tracker.check_cliches(final_text)
        if cliche_issues:
            ui.warn(f"[陈词滥调] 发现 {len(cliche_issues)} 处：{cliche_issues[:3]}")

        sentence_issues = tracker.check_sentence_patterns(final_text)
        if sentence_issues:
            ui.hint(f"[句式检查] {sentence_issues[:3]}")

        abstract_issues = tracker.check_abstract_nouns(final_text)
        if abstract_issues:
            ui.hint(f"[抽象名词] 发现 {len(abstract_issues)} 处：{abstract_issues[:5]}")

        # Save revised draft
        dirs = self.state_mgr.ensure_dirs(state.novel_name)
        new_revision = ch.revision_count + 1
        draft_path = dirs["drafts"] / f"chapter_{ch_num:02d}_r{new_revision}.txt"
        draft_path.write_text(final_text, encoding="utf-8")
        ch.draft_path = str(draft_path)
        ch.revision_count = new_revision

        # Update edited version
        edited_path = dirs["edited"] / f"chapter_{ch_num:02d}.txt"
        edited_path.write_text(final_text, encoding="utf-8")
        ch.edited_path = str(edited_path)

        # Update review status
        if review.get("approved", False):
            ch.review_status = "passed"
        else:
            ch.review_status = "needs_revision"
        ch.review_notes = json.dumps(review, ensure_ascii=False)

        # 展示八维质量评分（quality_breakdown 消费）
        breakdown = review.get("quality_breakdown", {})
        if breakdown:
            dim_names = {
                "opening_hook": "开头", "plot_progression": "剧情", "character_depth": "人物",
                "dialogue_quality": "对话", "ending_hook": "结尾", "pacing": "节奏",
                "show_not_tell": "展示", "language_quality": "语言",
            }
            dims = []
            for dim, label in dim_names.items():
                s = breakdown.get(dim)
                if s is not None:
                    dims.append(f"{label}={s}")
            total = breakdown.get("total")
            if total is not None:
                dims.append(f"总分={total}/80")
            if dims:
                ui.hint(f"[质量分维] {', '.join(dims)}")

        # Update summary and tracking
        ch.summary = self.ctx_mgr.generate_chapter_summary(final_text, ch_num)
        before = tracker.snapshot()
        tracker.update_tracking(ch_num, final_text, chapter_plan, review=review)
        if review.get("tracking_updates"):
            tracker.update_from_review(ch_num, review)
        after = tracker.snapshot()
        tracker.log_changes_csv(ch_num, before, after, source="revise")

        self.state_mgr.save(state)
        ui.success("修订已保存")

    def _collect_user_feedback(self) -> str:
        try:
            return prompt_multiline("请输入修改意见：")
        except UserAbort:
            return ""

    def _select_idea(self, ideas: list[dict], user_feedback: str):
        if not ideas:
            ui.warn("未能生成修改思路，将直接使用您的意见进行修订。")
            return user_feedback

        ui.section("修改思路", "请选择一个方向，或输入自定义修改方向", style="yellow")
        for i, idea in enumerate(ideas, 1):
            title = idea.get('title', '思路')
            desc = idea.get('description', '')
            effect = idea.get('expected_effect', '')
            notes = idea.get('consistency_notes', '')
            lines = [f"{i}. {title}"]
            if desc:
                lines.append(f"   {desc[:200]}{'...' if len(desc) > 200 else ''}")
            if effect:
                lines.append(f"   预期效果：{effect[:120]}")
            if notes and notes != '无':
                lines.append(f"   一致性提醒：{notes[:120]}")
            ui.info("\n".join(lines))

        ui.hint("0. 不使用以上思路，直接用我的原始意见")

        try:
            choice = prompt_single("\n请选择（输入编号或直接输入自定义修改方向）：")
        except UserAbort:
            return user_feedback

        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(ideas):
                selected = ideas[idx - 1]
                ui.success(f"已选择：{selected.get('title', '')}")
                return selected
            elif idx == 0:
                return user_feedback
            else:
                ui.warn("编号无效，使用原始意见")
                return user_feedback
        elif choice:
            return f"自定义修改方向：{choice}\n原始意见：{user_feedback}"
        else:
            return user_feedback

    def _get_adjacent_text(self, state: NovelState, ch_num: int) -> tuple[str, str]:
        dirs = self.state_mgr.ensure_dirs(state.novel_name)
        i = ch_num - 1
        prev_ending = ""
        next_opening = ""
        if i > 0:
            prev_ch = state.chapters[i - 1]
            prev_path = Path(prev_ch.edited_path) if prev_ch.edited_path else (Path(prev_ch.draft_path) if prev_ch.draft_path else None)
            if prev_path and prev_path.exists():
                prev_ending = prev_path.read_text(encoding="utf-8")[-800:]
        if i < state.total_chapters - 1:
            next_ch = state.chapters[i + 1]
            next_path = Path(next_ch.edited_path) if next_ch.edited_path else (Path(next_ch.draft_path) if next_ch.draft_path else None)
            if not next_path or not next_path.exists():
                next_path = dirs["drafts"] / f"chapter_{next_ch.chapter_number:02d}.txt"
            if next_path.exists():
                next_opening = next_path.read_text(encoding="utf-8")[:800]
        return prev_ending, next_opening

    def _find_chapter(self, state: NovelState, chapter_number: int):
        for ch in state.chapters:
            if ch.chapter_number == chapter_number:
                return ch
        return None
