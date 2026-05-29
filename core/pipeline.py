"""Pipeline orchestrator: coordinates all agents."""

import json
import logging
import signal
from difflib import SequenceMatcher
from pathlib import Path

import yaml

from agents.capability_extractor import CapabilityExtractor
from agents.critic import CriticAgent
from agents.director import DirectorAgent
from agents.editor import EditorAgent
from agents.outline_auditor import OutlineAuditor
from agents.outline_global_checker import OutlineGlobalChecker
from agents.plotter import BATCH_SIZE as PLOTTER_BATCH_SIZE
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
    REFINE_HOLISTIC_PROMPT, REFINE_STYLE_PROMPT,
    REFINE_REWRITE_DIRECTIVE,
)
from core.state_manager import ChapterState, NovelState, StateManager, VolumeDef, atomic_write_json
from core.tracker import Tracker
from core import ui

logger = logging.getLogger(__name__)


class _PhaseHandledError(Exception):
    """Phase handler 已向用户展示错误并保存进度，上层无需重复展示。"""
    def __init__(self, phase: str, original: Exception):
        self.phase = phase
        self.original = original
        super().__init__(str(original))


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
        self.capability_extractor = CapabilityExtractor(self.llm, self.config)
        self.outline_auditor = OutlineAuditor(self.llm, self.config)
        self.outline_global_checker = OutlineGlobalChecker(self.llm, self.config)

        self._interrupted = False
        self._current_state = None
        self._build_genre_strictness()
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
            "capability_extractor": self.capability_extractor,
            "outline_auditor": self.outline_auditor,
            "outline_global_checker": self.outline_global_checker,
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
            ui.hint("进度已保存，可在 Web 界面重新运行以恢复")

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
        except _PhaseHandledError:
            raise
        except Exception as e:
            logger.error(f"Pipeline error: {e}")
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
        except _PhaseHandledError:
            raise
        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            raise

    # 题材 → 审核严格度映射（从 config.yaml genre_strictness 构建）
    _GENRE_STRICTNESS: dict[str, str] = {}

    def _build_genre_strictness(self) -> None:
        cfg = self.config.get("genre_strictness", {})
        result = {}
        for level, keywords in cfg.items():
            for kw in keywords:
                result[kw] = level
        self._GENRE_STRICTNESS = result

    def _run_pipeline(self, state: NovelState) -> None:
        self._current_state = state

        # Phase 0: Styling
        if state.phase == "styling":
            try:
                style_desc = state.style_description or "传统文学风格，注重文笔和人物塑造"

                # 断点恢复：已有风格指南则直接进入精修，无需重新生成
                if not state.style_guide:
                    ui.info(f"[风格顾问] 正在根据风格描述生成指南：{style_desc}")
                    state.style_guide = self.style_advisor.run(style_desc, story_idea=state.story_idea)
                    if not state.style_guide:
                        ui.error("[风格顾问] 生成失败，请重试")
                        return
                    self.state_mgr.save(state)

                ui.section("风格指南确认", state.style_guide.get("style_name", "?"))

                def _save_style(r):
                    state.style_guide = r
                    self.state_mgr.save(state)

                refined_style = self._refine_block(
                    label="风格指南",
                    initial=state.style_guide,
                    system_prompt=REFINE_STYLE_PROMPT,
                    context_summary=self._build_style_context(state),
                    on_update=_save_style,
                )
                if self._interrupted:
                    state.style_guide = refined_style
                    self.state_mgr.save(state)
                    ui.hint("[中断] 风格指南调整已保存，恢复后可继续精修")
                    return

                state.style_guide = refined_style
                self._apply_style_temperatures(state.style_guide)
                self._apply_strictness(state)
                state.phase = "collecting_params"
                self.state_mgr.save(state)
                ui.success(f"[风格顾问] 风格指南已确认：{state.style_guide.get('style_name', '?')}")
            except Exception as e:
                logger.error(f"Styling phase error: {e}")
                self.state_mgr.save(state)
                ui.error("风格分析阶段出错")
                ui.hint("进度已保存，可在 Web 界面重新运行以恢复")
                raise _PhaseHandledError("styling", e) from e

        if self._interrupted:
            return

        # Phase 0.5: Collect params
        if state.phase == "collecting_params":
            try:
                self._collect_params(state)
            except Exception as e:
                logger.error(f"Collecting params phase error: {e}")
                self.state_mgr.save(state)
                ui.error("参数收集阶段出错")
                ui.hint("进度已保存，可在 Web 界面重新运行以恢复")
                raise _PhaseHandledError("collecting_params", e) from e

        if self._interrupted:
            return

        # 兼容旧 state：refining 已合并入 directing
        if state.phase == "refining":
            state.phase = "directing"
            self.state_mgr.save(state)

        # Phase 1: Directing (一次性生成 + 全量精修)
        if state.phase == "directing":
            try:
                self._run_directing_holistic(state)
            except Exception as e:
                logger.error(f"Directing phase error: {e}")
                self.state_mgr.save(state)
                ui.error("导演阶段出错")
                ui.hint("进度已保存，可在 Web 界面重新运行以恢复")
                raise _PhaseHandledError("directing", e) from e

        if self._interrupted:
            return

        # Phase 2: Plotting
        if state.phase == "plotting":
            if not self._checkpoint(state, f"拆分 {state.total_chapters} 章剧情计划（耗时较长）"):
                return
            ui.info("[编剧] 正在拆分章节和规划剧情...")

            # Engine A: 提取能力矩阵（如果尚未提取）
            if not state.capability_matrix:
                ui.info("[大纲审计] Engine A: 正在提取设定能力矩阵...")
                characters = (state.world_data or {}).get("characters", [])
                locations = (state.world_data or {}).get("locations", [])
                world_for_matrix = {k: v for k, v in (state.world_data or {}).items()
                                    if k not in ("characters", "locations")}
                state.capability_matrix = self.capability_extractor.run(
                    world_for_matrix, characters, locations,
                    style_guide=state.style_guide,
                )
                self.state_mgr.save(state)
                ui.success(f"[大纲审计] 能力矩阵已提取："
                           f"{len(state.capability_matrix.get('characters', {}))} 角色, "
                           f"{len(state.capability_matrix.get('locations', {}))} 地点")

            def _save_plotting_progress(plans):
                state.chapter_plans = list(plans)
                self.state_mgr.save(state)

            # 断点恢复：对齐拆章/审计两条进度线。崩溃可能落在「拆完 save」与
            # 「审完 save」之间，导致尾部批次拆了但没审。截断到已审章节数，让
            # plotter 重拆+重审那一批，保证两线一致、修正版不丢。
            audited_count = len(state.chapter_audits)
            if state.chapter_plans and len(state.chapter_plans) > audited_count:
                dropped = len(state.chapter_plans) - audited_count
                state.chapter_plans = state.chapter_plans[:audited_count]
                ui.hint(f"[恢复] 丢弃 {dropped} 章「拆了未审」的尾部，将重拆+重审该批")

            # 边拆边审：每拆完一批立即审计，审计重写后的修正版回填 plans，
            # 影响后续批次拆分。审计异常单独捕获，避免误判为拆章失败。
            def _on_batch(plans, batch_start, batch):
                _save_plotting_progress(plans)
                if self._interrupted:
                    return
                try:
                    self._audit_one_batch(state, plans, batch_start, batch)
                except Exception as e:
                    logger.error(f"Outline audit error (batch_start={batch_start}): {e}")
                    ui.warn("[大纲审计] 本批审计出错，已跳过审计，拆章继续")

            ui.section("大纲审计", f"共 {state.total_chapters} 章（边拆边审）")

            try:
                chapter_plans = self.plotter.run(
                    state.outline, state.world_data, state.total_chapters,
                    style_guide=state.style_guide, volumes=state.volumes,
                    existing_plans=state.chapter_plans,
                    on_batch_complete=_on_batch,
                )
            except Exception as e:
                logger.error(f"Plotting phase error: {e}")
                if state.chapter_plans is None:
                    state.chapter_plans = []
                self.state_mgr.save(state)
                ui.error("编剧阶段出错")
                ui.hint("进度已保存，可在 Web 界面重新运行以恢复")
                raise _PhaseHandledError("plotting", e) from e

            state.chapter_plans = chapter_plans

            novel_dir = self.state_mgr.get_novel_dir(state.novel_name)
            atomic_write_json(novel_dir / "chapters.json", chapter_plans)

            # 全部边拆边审完成后的收尾：Engine D3+D4 全局检查 + 汇总
            self._finalize_outline_audit(state, chapter_plans)
            if self._interrupted:
                return

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
                ui.error("写作阶段出错")
                ui.hint("进度已保存，可在 Web 界面重新运行以恢复")
                raise _PhaseHandledError("writing", e) from e

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
                ui.error("编辑阶段出错")
                ui.hint("进度已保存，可在 Web 界面重新运行以恢复")
                raise _PhaseHandledError("editing", e) from e

        # Phase 5: Combine final output
        if state.phase == "editing" and state.current_chapter >= state.total_chapters:
            self._combine_final(state)
            state.phase = "complete"
            self.state_mgr.save(state)
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
        import re
        ui.section("分卷规划", style="cyan")
        ui.info(f"共 {total_chapters} 章，正在生成分卷建议...")

        suggest_prompt = (
            f"故事灵感：{story_idea}\n\n"
            f"总章节数：{total_chapters}\n\n"
            f"请为这部小说设计分卷方案。每卷应有独立的叙事焦点和情感弧线。"
            f"卷的划分应基于故事的自然节奏（如地点转换、时间跳跃、阶段性的冲突与解决）。\n\n"
            f"输出 JSON 数组，按卷顺序排列：[{{\"title\": \"卷名（不要含'第N卷'前缀，只写卷名本身）\", "
            f"\"chapters\": \"起始章-结束章（如 1-8）\", \"reason\": \"分卷理由\"}}]\n"
            f"硬性要求：\n"
            f"1. 第一卷必须从第 1 章开始\n"
            f"2. 最后一卷必须以第 {total_chapters} 章结束\n"
            f"3. 卷与卷之间章节范围连续不重叠（如 [1-8, 9-16, 17-25]）\n"
            f"4. title 只写卷名本身（如\"觉醒\"），不要加\"第二卷\"\"卷二\"等前缀，前端会自动加卷号\n"
            f"5. 每卷建议 8-15 章\n"
            f"只输出 JSON，不要额外文字。"
        )
        result = self.llm.chat_json("你是一位小说结构规划师。", suggest_prompt, temperature=0.7)
        if not isinstance(result, list) or not result:
            ui.warn("分卷建议格式异常，跳过分卷")
            return None

        # 解析并清洗 title（去除 LLM 自加的"第N卷"前缀）
        _PREFIX_RE = re.compile(r"^(第[一二三四五六七八九十百零\d]+[卷部章]|卷[一二三四五六七八九十\d]+)[\s·:：、\-]*")
        suggestions = []
        for i, item in enumerate(result, 1):
            raw_title = (item.get("title") or f"卷{i}").strip()
            title = _PREFIX_RE.sub("", raw_title).strip() or f"卷{i}"
            chapters_str = item.get("chapters", "")
            reason = item.get("reason", "")
            try:
                parts = chapters_str.split("-")
                start = int(parts[0].strip())
                end = int(parts[1].strip())
            except (ValueError, IndexError):
                start = None
                end = None
            suggestions.append({"number": i, "title": title, "start": start, "end": end, "reason": reason})

        # 校验/修复 chapters 范围：必须从 1 起、严格递增、最后一卷到 total
        suggestions = self._normalize_volume_ranges(suggestions, total_chapters)
        if not suggestions:
            ui.warn("分卷范围异常无法修复，跳过分卷")
            return None

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

    @staticmethod
    def _normalize_volume_ranges(suggestions: list[dict], total_chapters: int) -> list[dict]:
        """校验并修复 LLM 给的分卷范围，确保从第 1 章起、连续、覆盖 total_chapters。

        Why: LLM 偶发输出范围有空洞（如 [11-15, 16-25]，丢失 1-10）或重叠 / 末尾
        不到 total，导致前端按 start_chapter 过滤章节时部分章节归不到任何卷，看起来
        像"缺第一卷"或"两个第二卷"。
        """
        if not suggestions:
            return suggestions
        # 按 start 排序（空值放最后）
        sortable = [s for s in suggestions if s.get("start") is not None]
        sortable.sort(key=lambda s: s["start"])
        unsortable = [s for s in suggestions if s.get("start") is None]
        # 给空范围的 item 平均分配剩余区间
        ordered = sortable + unsortable

        # 重建连续区间：从 1 开始顺次铺到 total
        n = len(ordered)
        if n == 0:
            return []
        avg = max(1, total_chapters // n)
        cursor = 1
        fixed = []
        for idx, s in enumerate(ordered):
            number = idx + 1
            # 强制 start = cursor，end 取 LLM 给的或平均长度
            llm_end = s.get("end")
            if llm_end is None or llm_end <= cursor:
                end = min(cursor + avg - 1, total_chapters)
            else:
                end = min(llm_end, total_chapters)
            # 最后一卷强制到 total
            if idx == n - 1:
                end = total_chapters
            if end < cursor:
                end = cursor
            fixed.append({
                "number": number,
                "title": s["title"],
                "start": cursor,
                "end": end,
                "reason": s.get("reason", ""),
            })
            cursor = end + 1
            if cursor > total_chapters and idx < n - 1:
                ui.warn(f"[分卷] 章节区间已用完，剩余 {n - 1 - idx} 卷未分配，已自动截断")
                break
        return fixed

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

    def _build_style_context(self, state: NovelState) -> str:
        """为风格指南精修构建上下文摘要（故事火花 + 用户原始风格描述）。"""
        parts: list[str] = []
        if state.story_idea:
            idea = state.story_idea.replace("\n", " ")
            parts.append(f"## 故事火花\n{idea[:800]}")
        if state.style_description:
            parts.append(f"## 用户风格描述\n{state.style_description}")
        return "\n\n".join(parts)

    def _build_holistic_context(self, state: NovelState) -> str:
        """为全量精修构建上下文（故事火花 + 风格偏好）。"""
        parts: list[str] = []
        if state.story_idea:
            idea = state.story_idea.replace("\n", " ")
            parts.append(f"## 故事火花\n{idea[:1000]}")
        if state.style_description:
            parts.append(f"## 风格偏好\n{state.style_description}")
        return "\n\n".join(parts)

    # ── 大纲审计（Plotting 阶段 Engine B→C→D）────────────────────────────

    def _build_audit_feedback(self, unapproved: list[tuple[int, dict]]) -> str:
        """从审计 issues 构建 Plotter 可读的反馈文本（对齐 Writer review-reject loop 的 feedback 构建）。"""
        parts = []
        for _, audit in unapproved:
            ch_num = audit.get("chapter_number", "?")
            title = audit.get("title", "")
            parts.append(f"### 第{ch_num}章「{title}」")

            # 问题列表
            issues = audit.get("issues", [])
            if issues:
                parts.append("\n#### 问题列表")
                for issue in issues:
                    severity = issue.get("severity", "unknown")
                    issue_type = issue.get("type", "unknown")
                    detail = issue.get("detail", "")
                    suggestion = issue.get("suggestion", "")
                    parts.append(f"- **[{severity}]** {issue_type}：{detail}")
                    if suggestion:
                        parts.append(f"  - 建议：{suggestion}")

            # 保留优点（quality_scores ≥ 7 的维度）
            qs = audit.get("quality_scores", {})
            strengths = [f"{dim}={score}" for dim, score in qs.items() if score >= 7]
            if strengths:
                parts.append(f"\n#### 保留优点\n{', '.join(strengths)}")

            parts.append("")  # 空行分隔

        return "\n".join(parts)

    def _audit_one_batch(
        self, state: NovelState, plans: list[dict], batch_start: int, batch: list[dict]
    ) -> None:
        """审计单个批次（边拆边审）：B+C 逐章交叉校验 + 重写循环 + D1+D2 批次检查。

        ★ 关键：plans 是 Plotter 的 all_plans 同一列表引用。重写后的章节计划必须
        原地 splice 回 plans，下一批拆分的 _build_existing_summaries(all_plans) 才能
        带上修正版，实现"前序审计修正影响后续拆分"。
        """
        # 跳过已审计的批次（断点恢复）
        already_audited = len(state.chapter_audits)
        if batch_start < already_audited:
            return

        audit_cfg = self.config.get("outline_audit", {})
        max_retries = audit_cfg.get("audit_max_retries", 2)
        stale_threshold = audit_cfg.get("stale_similarity_threshold", 0.92)
        auto_rewrite = audit_cfg.get("auto_rewrite", True)
        batch_size = audit_cfg.get("batch_size", PLOTTER_BATCH_SIZE)

        novel_dir = self.state_mgr.get_novel_dir(state.novel_name)
        ch_range = f"{batch[0].get('chapter_number', '?')}-{batch[-1].get('chapter_number', '?')}"
        ui.info(f"[大纲审计] Engine B+C: 审核第 {ch_range} 章...")

        audits = self.outline_auditor.run(
            batch, state.capability_matrix or {},
            state.outline or {}, style_guide=state.style_guide,
        )

        # 推送每章审计结果到前端
        for audit in audits:
            ui.show_chapter_audit(audit.get("chapter_number", 0), audit.get("title", ""), audit)

        # ── 重写循环 ──
        retries = 0
        quality_history: list[float] = []
        stale = False

        while auto_rewrite:
            unapproved = [(i, a) for i, a in enumerate(audits) if not a.get("approved")]
            if not unapproved:
                break
            if retries >= max_retries:
                ui.warn(f"[大纲审计] 已达 audit_max_retries={max_retries} 上限，接受当前版本")
                break

            retries += 1
            failed_ch_nums = [a.get("chapter_number") for _, a in unapproved]
            ui.warn(f"[大纲审计] {len(unapproved)} 章未通过，第{retries}次重写：第{failed_ch_nums}章")

            # 构建反馈
            feedback = self._build_audit_feedback(unapproved)
            if stale:
                feedback += (
                    "\n\n[系统检测] 上次重写几乎未修改内容，本次必须进行实质性改写。"
                    "不允许仅做同义替换或微调措辞，必须大幅重组情节点和叙事方式。"
                )

            # 质量停滞检测
            avg_quality = sum(a.get("total_quality", 0) for a in audits) / len(audits)
            quality_history.append(avg_quality)
            if len(quality_history) >= 2 and quality_history[-1] <= quality_history[-2]:
                ui.warn(f"[大纲审计] 质量分停滞（{quality_history[-2]:.1f}→{quality_history[-1]:.1f}），接受当前版本")
                break

            # 获取旧计划
            old_plans = [plans[batch_start + i] for i, _ in unapproved]

            # 调用 Plotter 重写
            new_plans = self.plotter.regenerate_chapters(
                plans, failed_ch_nums, feedback, old_plans,
                state.world_data, state.outline, style_guide=state.style_guide,
            )

            # 相似度检测
            old_json = json.dumps(old_plans, ensure_ascii=False, sort_keys=True)
            new_json = json.dumps(new_plans, ensure_ascii=False, sort_keys=True)
            similarity = SequenceMatcher(None, old_json, new_json).ratio()
            stale = similarity > stale_threshold
            if stale:
                ui.warn(f"[大纲审计] 重写相似度 {similarity:.0%}，内容几乎未修改")

            # 每轮保存版本文件
            for r_idx, (batch_idx, _) in enumerate(unapproved):
                ch_num = failed_ch_nums[r_idx]
                version_path = novel_dir / f"chapter_plans_{ch_num:02d}_r{retries}.json"
                atomic_write_json(version_path, new_plans[r_idx])

            # ★ splice 回 plans（Plotter 的 all_plans 引用），使修正版传播到后续批次
            for new_plan in new_plans:
                ch_num = new_plan.get("chapter_number")
                for idx, p in enumerate(plans):
                    if p.get("chapter_number") == ch_num:
                        plans[idx] = new_plan
                        break

            # 重新审计整个批次（不只是重写的章节，保证级联一致性）
            new_batch = plans[batch_start:batch_start + batch_size]
            new_audits = self.outline_auditor.run(
                new_batch, state.capability_matrix or {},
                state.outline or {}, style_guide=state.style_guide,
            )
            for audit in new_audits:
                ui.show_chapter_audit(audit.get("chapter_number", 0), audit.get("title", ""), audit)

            # 记录 revision_count 到审计结果
            for audit in new_audits:
                if audit.get("chapter_number") in failed_ch_nums:
                    audit["revision_count"] = retries

            audits = new_audits

        # ── 人工干预：仅在循环结束后仍有问题时暂停 ──
        still_unapproved = [a for a in audits if not a.get("approved")]
        if still_unapproved and retries > 0:
            failed_names = [f"第{a.get('chapter_number')}章「{a.get('title', '')}」" for a in still_unapproved]
            ui.warn(f"[大纲审计] 自动重写后仍有 {len(still_unapproved)} 章未通过：{', '.join(failed_names)}")

            audit_summary = {
                "batch_range": ch_range,
                "approved_count": len(audits) - len(still_unapproved),
                "unapproved_count": len(still_unapproved),
                "audits": audits,
            }
            refined_summary = self._refine_block(
                label=f"大纲审计结果（第 {ch_range} 章）",
                initial=audit_summary,
                system_prompt=self.outline_auditor.system_prompt,
                context_summary=json.dumps(audit_summary, ensure_ascii=False, indent=2),
            )
            if isinstance(refined_summary, dict) and "audits" in refined_summary:
                audits = refined_summary["audits"]

        # 保存本批审计结果
        state.chapter_audits.extend(audits)

        # Engine D1+D2: 批次级检查（遗忘曲线 + 节奏曲线）
        ui.info("[大纲审计] Engine D1+D2: 批次级检查...")
        thresholds = self._get_audit_thresholds(state)
        batch_summary = self.outline_global_checker.run_batch(
            plans[:batch_start + len(batch)],
            state.capability_matrix or {},
            state.outline or {},
            style_guide=state.style_guide,
            thresholds=thresholds,
        )
        state.batch_audits.append({**batch_summary, "batch_range": ch_range})
        ui.show_batch_audit(ch_range, batch_summary)

        self.state_mgr.save(state)

    def _finalize_outline_audit(self, state: NovelState, chapter_plans: list[dict]) -> None:
        """全部章节边拆边审完成后的收尾：Engine D3+D4 全局检查 + 审计汇总。"""
        # Engine D3+D4: 全局级检查（完整性 + 跨批次一致性）
        if not state.global_audit:
            ui.info("[大纲审计] Engine D3+D4: 全局完整性扫描...")
            thresholds = self._get_audit_thresholds(state)
            state.global_audit = self.outline_global_checker.run_global(
                chapter_plans, state.capability_matrix or {},
                state.outline or {},
                style_guide=state.style_guide,
                thresholds=thresholds,
            )
            ui.show_global_audit(state.global_audit)
            self.state_mgr.save(state)

        # 审计汇总
        total_issues = sum(len(a.get("issues", [])) for a in state.chapter_audits)
        major_count = sum(
            1 for a in state.chapter_audits
            for i in a.get("issues", []) if i.get("severity") == "major"
        )
        approved_count = sum(1 for a in state.chapter_audits if a.get("approved"))
        ui.success(
            f"[大纲审计] 完成: {approved_count}/{len(state.chapter_audits)} 章通过, "
            f"{total_issues} 个问题 (major={major_count})"
        )


    def _get_audit_thresholds(self, state: NovelState) -> dict:
        """获取遗忘检测阈值，优先从 style_guide 获取，否则用默认值。"""
        thresholds = (state.style_guide or {}).get("suggestions", {}).get("tracking_thresholds", {})
        return {
            "character": thresholds.get("character", 10),
            "plotline": thresholds.get("plotline", 12),
            "foreshadowing": thresholds.get("foreshadowing", 20),
        }

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
                    # 检查是否被中断（用户刷新页面）
                    if self._interrupted:
                        return result
                    if new_result is None:
                        ui.warn("打磨失败，保留当前版本")
                        continue
                    # 调整后如果与原版几乎一致，自动升温重试一次（避免"调整无变化"）
                    if self._refine_too_similar(result, new_result):
                        ui.warn(f"检测到「{label}」调整后变化过小，自动升温重试...")
                        retry = self._llm_refine(
                            system_prompt,
                            label=label,
                            current=result,
                            user_feedback=action + "\n\n（上一次调整后输出几乎未变，请彻底重写涉及部分，与原版表述明显不同）",
                            context=context_summary,
                            force_rewrite=True,
                        )
                        # 检查是否被中断
                        if self._interrupted:
                            return result
                        if retry is not None:
                            new_result = retry
                            if self._refine_too_similar(result, new_result):
                                ui.warn(f"AI 仍未给出明显不同的版本，保留当前结果（可选'重写'换方向）")
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
                # 检查是否被中断
                if self._interrupted:
                    return result
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
                    rewrite: bool = False, previous=None,
                    force_rewrite: bool = False):
        """根据 user_feedback 调整 current；
        rewrite=True 时整块重生成（previous 作为反上下文，升温 0.9）。
        force_rewrite=True 时在 adjust 路径上加"换措辞/换节奏"约束并升温（用于自动升温重试）。

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
            extra = ""
            if force_rewrite:
                extra = (
                    "\n\n注意：必须**实质性**修改，输出与当前版本明显不同；只换同义词或调标点会被判定为失败。"
                )
            user_msg = (
                f"## 上下文\n{context}\n\n"
                f"## 当前版本\n{json.dumps(current, ensure_ascii=False, indent=2)}\n\n"
                f"## 用户反馈\n{user_feedback}{extra}\n\n"
                f"请根据反馈调整「{label}」，输出完整修订后的 JSON（结构与当前版本一致）。"
            )
            sys_msg = system_prompt
            temperature = 0.9 if force_rewrite else 0.7
        try:
            return self.llm.chat_json(sys_msg, user_msg, temperature=temperature)
        except Exception as e:
            logger.warning(f"_llm_refine failed for {label}: {e}")
            return None

    @staticmethod
    def _refine_too_similar(old, new, threshold: float = 0.92) -> bool:
        """判定两版 refine 结果是否高度相似（用于"调整无变化"防御）。"""
        if old is None or new is None:
            return False
        try:
            old_s = json.dumps(old, ensure_ascii=False, sort_keys=True)
            new_s = json.dumps(new, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError):
            old_s, new_s = str(old), str(new)
        if not old_s or not new_s:
            return False
        return SequenceMatcher(None, old_s, new_s).ratio() >= threshold

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
        if not rules or "validation_tasks" not in rules:
            logger.warning("validation_rules.json not initialized, skipping level application")
            return
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

    @staticmethod
    def _rewrite_similarity(old: str, new: str) -> float:
        """计算两段文本的相似度 (0-1)。"""
        return SequenceMatcher(None, old, new).ratio()

    def _write_chapters(self, state: NovelState) -> None:
        # I2: review-rewrite 循环硬上限。即便审稿一直 reject，也最多重写 max_retries 次后接受当前版本
        max_retries = self.config["novel"]["review_max_retries"]
        words_min, words_max = self._get_words_range(state)
        tracker = Tracker(self.state_mgr.get_novel_dir(state.novel_name), novel_name=state.novel_name)

        for i in range(state.current_chapter, state.total_chapters):
            if self._interrupted:
                return

            if i >= len(state.chapter_plans) or i >= len(state.chapters):
                ui.warn(f"[警告] 章节索引 {i} 超出范围（计划 {len(state.chapter_plans)} 章，状态 {len(state.chapters)} 章），跳过")
                continue
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
            tracking_ctx = tracker.get_tracking_context(
                ch_num,
                max_chars=self.config.get("context_budget", {}).get("tracking_context_chars", 8000),
            )

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
            recent_excerpts = self._collect_recent_excerpts(state, i)
            relevant_anchors = tracker.query_relevant(
                plan, ch_num,
                top_k=self.config.get("context_budget", {}).get("foreshadowing_top_k", 8),
            )
            running_ctx = self.ctx_mgr.build_running_context(
                state.world_data, state.outline, completed_summaries, plan,
                tracking_context=tracking_ctx, story_idea=state.story_idea,
                volumes=state.volumes,
                volume_summaries=state.volume_summaries,
                recent_chapter_excerpts=recent_excerpts,
                relevant_anchors=relevant_anchors,
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
                applied = fix_result.get("fixes", {}).get("applied", [])
                if applied:
                    draft = fix_result["text"]
                    fixed = True
                    ui.hint(f"[追踪] 自动修正角色名：{applied}")

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
            quality_history: list[int] = []
            stale_rewrite = False
            while not review.get("approved", False) and retries < max_retries:
                retries += 1
                issues = review.get("issues", [])
                if not issues:
                    logger.warning(f"Review not approved but no issues listed, injecting fallback issue")
                    issues = [{"severity": "major", "description": "审核未通过但未列出具体问题，可能存在整体质量问题",
                               "suggestion": "请对全章进行全面审查，重点关注叙事逻辑、人物一致性和语言质量"}]
                    review["issues"] = issues
                major = [i for i in issues if i.get("severity") == "major"]
                ui.warn(f"[审核] 发现 {len(major)} 个主要问题，第{retries}次重写...")

                feedback = "\n".join(
                    f"- [{i.get('severity')}] {i.get('description')}"
                    + (f"（位置：{i.get('location')}）" if i.get('location') else "")
                    + f" → 建议：{i.get('suggestion')}"
                    for i in issues
                )
                strengths = review.get("strengths", [])
                if strengths:
                    feedback += "\n\n以下部分写得很好，重写时请保留：\n" + "\n".join(
                        f"- {s}" for s in strengths
                    )

                # 升级策略：上次重写几乎未修改 或 质量分停滞时加压
                if stale_rewrite:
                    feedback += (
                        "\n\n[系统检测] 上次重写几乎未修改内容，本次必须进行实质性改写。"
                        "不允许仅做同义替换或微调措辞，必须大幅重组段落结构和叙事方式。"
                    )

                # 质量分趋势检测：连续两轮未上升则提前终止
                current_total = (review.get("quality_breakdown") or {}).get("total")
                if current_total is not None:
                    quality_history.append(current_total)
                if len(quality_history) >= 2 and quality_history[-1] <= quality_history[-2]:
                    ui.warn(f"[审核] 质量分停滞（{quality_history[-2]}→{quality_history[-1]}），重写可能无效，接受当前版本")
                    break

                old_draft = draft
                draft = self.writer.rewrite(draft, feedback, plan, running_ctx, style_guide=state.style_guide, words_min=words_min, words_max=words_max)

                # 变化检测
                similarity = self._rewrite_similarity(old_draft, draft)
                stale_rewrite = similarity > 0.92
                if stale_rewrite:
                    ui.warn(f"[审核] 重写相似度 {similarity:.0%}，内容几乎未修改")
                    logger.info(f"Chapter {ch_num} rewrite #{retries} similarity={similarity:.2f}")

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
                    self._maybe_generate_volume_summary(state, ch_num)
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

            if i >= len(state.chapters):
                ui.warn(f"[警告] 编辑阶段章节索引 {i} 超出范围（共 {len(state.chapters)} 章），跳过")
                continue
            ch = state.chapters[i]
            ch_num = ch.chapter_number
            ui.info(f"[编辑] 润色第 {ch_num}/{state.total_chapters} 章...")

            # Read the final draft (may have been revised)
            draft_path = Path(ch.draft_path) if ch.draft_path else dirs["drafts"] / f"chapter_{ch_num:02d}.txt"
            draft = draft_path.read_text(encoding="utf-8")

            # Get tracking context for consistency during editing
            tracking_ctx = tracker.get_tracking_context(
                ch_num,
                max_chars=self.config.get("context_budget", {}).get("tracking_context_chars", 8000),
            )

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
        applied = fix_result.get("fixes", {}).get("applied", [])
        if applied:
            final_text = fix_result["text"]
            fixed = True
            ui.hint(f"[追踪] 自动修正角色名：{applied}")

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

    def _collect_recent_excerpts(self, state: NovelState, current_index: int, max_chars_per_ch: int = 1500) -> list[str]:
        """收集最近 N 章原文片段（Level 1 近端记忆），用于让 Writer 感知文风延续。

        Why: 单靠摘要会让 Writer 漂移到通用网文腔。原文片段保留原作笔触、人物口吻、意象。
        How to apply: 取每章首尾各 750 字（max_chars_per_ch=1500），合并段落断裂处。
        """
        n = self.ctx_mgr.recent_chapters_full
        excerpts: list[str] = []
        start = max(0, current_index - n)
        for j in range(start, current_index):
            ch = state.chapters[j]
            path = None
            for p in (ch.edited_path, ch.draft_path):
                if p and Path(p).exists():
                    path = Path(p)
                    break
            if not path:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            if len(text) <= max_chars_per_ch:
                excerpts.append(text)
            else:
                half = max_chars_per_ch // 2
                excerpts.append(text[:half] + "\n…(中略)…\n" + text[-half:])
        return excerpts

    def _maybe_generate_volume_summary(self, state: NovelState, ch_num: int) -> None:
        """如果 ch_num 是某卷最后一章，生成该卷的 Level 3 卷级摘要并存入 state。

        Why: 卷级摘要是 300 章场景的长程记忆，避免章节摘要线性堆积爆 token。
        How to apply: 仅在 advance_volume 触发卷切换时调用一次；存量 state 可补生成。
        """
        if not state.volumes:
            return
        # 找到 ch_num 所在卷
        cur_vol = None
        for vol in state.volumes:
            if vol.start_chapter <= ch_num <= vol.end_chapter:
                cur_vol = vol
                break
        if not cur_vol or ch_num != cur_vol.end_chapter:
            return  # 只在卷末触发
        if state.volume_summaries is None:
            state.volume_summaries = {}
        if cur_vol.number in state.volume_summaries:
            return  # 已生成
        # 收集本卷所有章节摘要
        vol_chapter_summaries = [
            c.summary for c in state.chapters
            if cur_vol.start_chapter <= c.chapter_number <= cur_vol.end_chapter and c.summary
        ]
        if len(vol_chapter_summaries) < self.ctx_mgr.volume_summary_min_chapters:
            return
        ui.info(f"[卷摘要] 生成第{cur_vol.number}卷「{cur_vol.title}」宏观摘要...")
        try:
            vs = self.ctx_mgr.generate_volume_summary(
                cur_vol.number, cur_vol.title, vol_chapter_summaries, state.style_guide,
            )
            if vs:
                state.volume_summaries[cur_vol.number] = vs
                ui.success(f"[卷摘要] 第{cur_vol.number}卷宏观摘要已生成（{len(vs)} 字）")
        except Exception as e:
            logger.warning(f"Volume summary generation failed for vol {cur_vol.number}: {e}")
