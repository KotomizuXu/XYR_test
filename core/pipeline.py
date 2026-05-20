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
from core.state_manager import ChapterState, NovelState, StateManager
from core.tracker import Tracker

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
        signal.signal(signal.SIGINT, self._handle_interrupt)

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
        print(f"[追踪系统] 审核严格度：{strictness}（题材：{genre or '未识别'}）")

    def _handle_interrupt(self, signum, frame):
        print("\n\n收到中断信号，正在保存进度...")
        self._interrupted = True

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

        print(f"\n{'='*60}")
        print(f"开始创作《{novel_name}》")
        print(f"故事灵感：{story_idea}")
        print(f"{'='*60}\n")

        try:
            self._run_pipeline(state)
        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            print(f"\n发生错误：{e}")
            print(f"进度已保存，可使用 'continue' 继续")
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

        self._apply_style_temperatures(state.style_guide)

        try:
            self._run_pipeline(state)
        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            print(f"\n发生错误：{e}")
            print(f"进度已保存，可使用 'continue' 继续")
            raise

    # 题材 → 审核严格度映射
    _GENRE_STRICTNESS = {
        "悬疑": "strict", "推理": "strict", "历史": "strict", "严肃": "strict",
        "爽文": "flexible", "复仇": "flexible", "言情": "flexible", "甜文": "flexible",
        "虐文": "flexible", "网文": "flexible", "玄幻": "flexible", "仙侠": "flexible",
    }

    def _run_pipeline(self, state: NovelState) -> None:
        # Phase 0: Styling
        if state.phase == "styling":
            style_desc = state.style_description or "传统文学风格，注重文笔和人物塑造"
            print(f"[风格顾问] 正在根据风格描述生成指南：{style_desc}")
            state.style_guide = self.style_advisor.run(style_desc, story_idea=state.story_idea)
            self._apply_style_temperatures(state.style_guide)
            # 根据题材自动设置审核严格度
            self._apply_strictness(state)
            state.phase = "collecting_params"
            self.state_mgr.save(state)
            print(f"[风格顾问] 风格指南已生成：{state.style_guide.get('style_name', '?')}\n")

        if self._interrupted:
            return

        # Phase 0.5: Collect params
        if state.phase == "collecting_params":
            self._collect_params(state)

        if self._interrupted:
            return

        # Phase 1: Directing
        if state.phase == "directing":
            print("[导演] 正在构建世界观和大纲...")
            result = self.director.run(state.story_idea, state.total_chapters, style_guide=state.style_guide)
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
            chapter_plans = self.plotter.run(state.outline, state.world_data, state.total_chapters, style_guide=state.style_guide)
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

        # Phase 2.5: Initialize tracking system (always ensure tracking files exist)
        if state.phase == "writing":
            tracker = Tracker(self.state_mgr.get_novel_dir(state.novel_name), novel_name=state.novel_name)
            if not tracker._read_json("character_state.json"):
                print("[追踪系统] 正在初始化追踪数据...")
                tracker.init_tracking(state.world_data, state.outline, state.chapter_plans)
                self._apply_validation_level(tracker)
                print("[追踪系统] 追踪数据已初始化（角色状态、时间线、情节线、伏笔、关系网络）\n")

        if self._interrupted:
            return

        # Phase 3: Writing + Reviewing loop
        if state.phase == "writing":
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

        print(f"根据「{state.style_guide.get('style_name', '?')}」风格，以下是写作参数建议：\n")

        if pace_desc:
            print(f"  节奏建议：{pace_desc}")
        if reward_desc:
            print(f"  反馈密度：{reward_desc}")
        print()

        print(f"  总章数：建议 {rec_chapters} 章")
        if chapters_reason:
            print(f"     理由：{chapters_reason}")

        print(f"  每章字数：建议 {rec_min}-{rec_max} 字")
        if words_reason:
            print(f"     理由：{words_reason}")
        print()

        # Collect user input
        print("请确认或调整以下参数：\n")

        def _read_int(prompt: str, default: int) -> int:
            while True:
                raw = input(prompt).strip()
                if not raw:
                    return default
                try:
                    return int(raw)
                except ValueError:
                    print(f"    请输入有效数字（直接回车使用默认值 {default}）")

        total_chapters = _read_int(f"  总章数（直接回车使用建议值 {rec_chapters}）：", rec_chapters)
        words_min = _read_int(f"  每章最少字数（直接回车使用建议值 {rec_min}）：", rec_min)
        words_max = _read_int(f"  每章最多字数（直接回车使用建议值 {rec_max}）：", rec_max)

        state.total_chapters = total_chapters
        state.novel_params = {
            "total_chapters": total_chapters,
            "words_per_chapter": {"min": words_min, "max": words_max},
        }
        state.phase = "directing"
        self.state_mgr.save(state)

        # 遗忘检测阈值
        sug_thresholds = suggestions.get("tracking_thresholds", {})
        rec_char = sug_thresholds.get("character", max(3, total_chapters // 3))
        rec_plot = sug_thresholds.get("plotline", max(4, total_chapters * 2 // 5))
        rec_foreshadow = sug_thresholds.get("foreshadowing", max(5, total_chapters // 2))
        threshold_reason = sug_thresholds.get("reason", "")

        print(f"\n  遗忘检测阈值：角色 {rec_char} 章 / 支线 {rec_plot} 章 / 伏笔 {rec_foreshadow} 章")
        if threshold_reason:
            print(f"     理由：{threshold_reason}")

        confirm = input(f"  直接回车确认，或输入自定义值（格式：角色,支线,伏笔）：").strip()
        if confirm:
            parts = confirm.replace("，", ",").split(",")
            if len(parts) == 3:
                try:
                    rec_char, rec_plot, rec_foreshadow = int(parts[0]), int(parts[1]), int(parts[2])
                except ValueError:
                    print("     格式错误，使用建议值")

        tracker = Tracker(self.state_mgr.get_novel_dir(state.novel_name), novel_name=state.novel_name)
        tracker.set_threshold("character", rec_char)
        tracker.set_threshold("plotline", rec_plot)
        tracker.set_threshold("foreshadowing", rec_foreshadow)
        print(f"  已设置阈值：角色 {rec_char} / 支线 {rec_plot} / 伏笔 {rec_foreshadow}")

        # Disabled checks configuration
        print("\n  可选：禁用特定检查类别（character/timeline/worldbuilding/locations）")
        disabled_input = input("  输入要禁用的类别（逗号分隔，直接回车全部启用）：").strip()
        if disabled_input:
            disabled = [d.strip() for d in disabled_input.replace("，", ",").split(",") if d.strip()]
            config = tracker._read_json("config.json")
            config["disabled_checks"] = disabled
            tracker._write_json("config.json", config)
            print(f"  已禁用检查：{disabled}")

        print(f"\n  确认参数：{total_chapters}章，{words_min}-{words_max}字/章\n")

    def _get_words_range(self, state: NovelState) -> tuple[int, int]:
        if state.novel_params and "words_per_chapter" in state.novel_params:
            wp = state.novel_params["words_per_chapter"]
            return wp["min"], wp["max"]
        cfg = self.config["novel"]["words_per_chapter"]
        return cfg["min"], cfg["max"]

    def _handle_retire(self, forgotten: dict, tracker: Tracker) -> None:
        """Allow user to retire forgotten elements they no longer want tracked."""
        try:
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

            print("  可选操作：输入编号退休（不再追踪）对应元素，直接回车跳过：")
            for idx, (_, _, desc) in enumerate(all_items, 1):
                print(f"    {idx}. 退休 {desc}")
            choice = input("  > ").strip()
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(all_items):
                    etype, name, desc = all_items[idx]
                    tracker.retire_element(etype, name)
                    print(f"  已退休：{desc}")
        except (KeyboardInterrupt, EOFError):
            print()

    def _apply_validation_level(self, tracker: Tracker) -> None:
        """Set validation level based on strictness config."""
        strictness = tracker._get_strictness()
        level = "deep" if strictness == "strict" else "standard"
        rules = tracker._read_json("validation_rules.json")
        rules["active_validation_level"] = level
        tracker._write_json("validation_rules.json", rules)

    def _report_forgotten(self, forgotten: dict) -> None:
        print("  [遗忘检测] 发现以下元素需要关注：")
        for char in forgotten.get("characters", []):
            print(f"    ⚠️ 角色「{char['name']}」已{char['chapters_absent']}章未出场（上次：第{char['last_seen']}章）")
        for plotline in forgotten.get("plotlines", []):
            print(f"    ⚠️ 支线「{plotline['name']}」停滞中（状态：{plotline.get('status', '?')}）")
        for fs in forgotten.get("foreshadowing", []):
            content = fs.get('content', '')
            print(f"    ⚠️ 伏笔「{content[:30]}...」已{fs['chapters_since']}章未回收（埋设于第{fs['planted_chapter']}章）")

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
            print(f"  [写前检查] ⚠️ 缺失数据：{missing}，继续写作但可能影响一致性")

        # Report validation level
        if checks["validation_rules"]:
            strictness = tracker._get_strictness()
            print(f"  [写前检查] 验证模式：{strictness}")

        # Extract key principle summaries for writer context
        if checks["style_guide"] and state.style_guide:
            style_name = state.style_guide.get("style_name", "")
            tone = state.style_guide.get("tone", {}).get("overall", "")
            if style_name:
                print(f"  [写前检查] 风格：{style_name}")
            reqs = state.style_guide.get("requirements", {}).get("detected", [])
            if reqs:
                print(f"  [写前检查] 写作规范：{', '.join(reqs)}")
            dealbreakers = state.style_guide.get("review", {}).get("dealbreakers", [])
            if dealbreakers:
                print(f"  [写前检查] 红线：{', '.join(str(d) for d in dealbreakers[:3])}")
            style_rules = state.style_guide.get("style_presets", {}).get("style_rules", [])
            if style_rules:
                print(f"  [写前检查] 文风要点：{'; '.join(str(r) for r in style_rules[:3])}")

        # Extract key character states
        char_state = tracker._read_json("character_state.json")
        if char_state:
            protag = char_state.get("protagonist", {})
            if protag.get("name"):
                phase = protag.get("development", {}).get("currentPhase", "")
                loc = protag.get("currentStatus", {}).get("location", "")
                print(f"  [写前检查] 主角{protag['name']}：阶段={phase}，位置={loc or '未知'}")

    def _write_chapters(self, state: NovelState) -> None:
        max_retries = self.config["novel"]["review_max_retries"]
        words_min, words_max = self._get_words_range(state)
        tracker = Tracker(self.state_mgr.get_novel_dir(state.novel_name), novel_name=state.novel_name)

        for i in range(state.current_chapter, state.total_chapters):
            if self._interrupted:
                return

            plan = state.chapter_plans[i]
            ch = state.chapters[i]
            ch_num = ch.chapter_number

            print(f"\n--- 第{ch_num}章：「{ch.title}」---")

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
                tracking_context=tracking_ctx,
            )

            # Write draft
            print(f"  [作家] 正在撰写...")
            draft = self.writer.run(plan, running_ctx, style_guide=state.style_guide, words_min=words_min, words_max=words_max)

            # Save draft
            dirs = self.state_mgr.ensure_dirs(state.novel_name)
            draft_path = dirs["drafts"] / f"chapter_{ch_num:02d}.txt"
            draft_path.write_text(draft, encoding="utf-8")
            ch.draft_path = str(draft_path)

            # Programmatic checks: character name alias fix
            fixed = False
            fix_result = tracker.auto_fix(draft, ch_num)
            if fix_result["fixes"]["applied"]:
                draft = fix_result["text"]
                fixed = True
                print(f"  [追踪] 自动修正角色名：{fix_result['fixes']['applied']}")

            # Programmatic checks: banned AI words auto-fix
            fixed_draft, banned_changes = tracker.auto_fix_banned_words(draft, state.style_guide)
            if banned_changes:
                draft = fixed_draft
                fixed = True
                print(f"  [禁用词] 自动修正 {len(banned_changes)} 处：{banned_changes[:5]}")

            # Programmatic checks: cliché/sentence/abstract patterns (report only)
            cliche_issues = tracker.check_cliches(draft)
            if cliche_issues:
                print(f"  [陈词滥调] 发现 {len(cliche_issues)} 处：{cliche_issues[:3]}")

            sentence_issues = tracker.check_sentence_patterns(draft)
            if sentence_issues:
                print(f"  [句式检查] {sentence_issues[:3]}")

            abstract_issues = tracker.check_abstract_nouns(draft)
            if abstract_issues:
                print(f"  [抽象名词] 发现 {len(abstract_issues)} 处：{abstract_issues[:5]}")

            if fixed:
                draft_path.write_text(draft, encoding="utf-8")

            # Review with tracking context for consistency checking
            print(f"  [审核] 正在审稿（含一致性校验）...")
            review = self.reviewer.run(draft, plan, state.world_data, style_guide=state.style_guide, tracking_context=tracking_ctx)
            ch.review_notes = json.dumps(review, ensure_ascii=False)

            # Save review report
            review_path = dirs["reviews"] / f"chapter_{ch_num:02d}_review.json"
            review_path.write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")

            retries = 0
            while not review.get("approved", False) and retries < max_retries:
                retries += 1
                issues = review.get("issues", [])
                if not issues:
                    logger.warning(f"Review not approved but no issues listed, accepting as-is")
                    break
                major = [i for i in issues if i.get("severity") == "major"]
                print(f"  [审核] 发现 {len(major)} 个主要问题，第{retries}次重写...")

                feedback = "\n".join(
                    f"- [{i.get('severity')}] {i.get('description')} → 建议：{i.get('suggestion')}"
                    for i in issues
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
                print(f"  [审核] 通过！质量评分：{review.get('overall_quality', '?')}/10，一致性：{calc_score}%")
                consistency = review.get("consistency_checks", {})
                if consistency:
                    for key in ("character_issues", "world_issues", "timeline_issues",
                                "physical_traits_issues", "personality_issues", "knowledge_state_issues"):
                        issues = consistency.get(key, [])
                        if issues:
                            print(f"  [一致性] {key}：{issues}")
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
                        print(f"  [自动修复] 审核建议修复 {len(applied)} 处：{applied[:3]}")
            else:
                ch.review_status = "needs_revision"
                print(f"  [审核] 达到最大重试次数，接受当前版本")

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
                print(f"  [追踪] 正在分析角色成长弧线...")
                completed_summaries = [c.summary for c in state.chapters[:i + 1] if c.summary]
                tracker.analyze_development(self.llm, completed_summaries, state.total_chapters, ch_num)

            after = tracker.snapshot()
            tracker.log_changes_csv(ch_num, before, after)

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
        tracker = Tracker(self.state_mgr.get_novel_dir(state.novel_name), novel_name=state.novel_name)

        for i in range(state.current_chapter, state.total_chapters):
            if self._interrupted:
                return

            ch = state.chapters[i]
            ch_num = ch.chapter_number
            print(f"  [编辑] 润色第{ch_num}章...")

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
        full_path.write_text("".join(combined_parts), encoding="utf-8")
        print(f"  全文已合并保存至：{full_path}")

    # ── Revise flow ──────────────────────────────────────────────

    def revise_chapter(self, novel_name: str, chapter_number: int) -> None:
        state = self.state_mgr.load(novel_name)
        if state is None:
            print(f"未找到小说《{novel_name}》，请检查名称")
            return

        ch = self._find_chapter(state, chapter_number)
        if ch is None:
            print(f"第{chapter_number}章不存在")
            return

        draft_path = Path(ch.edited_path) if ch.edited_path else (Path(ch.draft_path) if ch.draft_path else None)
        if not draft_path or not draft_path.exists():
            print(f"第{chapter_number}章尚未完成，无法修订")
            return

        draft = draft_path.read_text(encoding="utf-8")

        print(f"\n--- 修订第{chapter_number}章：「{ch.title}」---")
        print(f"当前版本：{len(draft)} 字")

        try:
            user_feedback = self._collect_user_feedback()
        except (KeyboardInterrupt, EOFError):
            print("\n已取消输入，退出修订")
            return

        if not user_feedback:
            print("未输入修改意见，退出修订")
            return

        self._apply_style_temperatures(state.style_guide)

        try:
            tracker = Tracker(self.state_mgr.get_novel_dir(novel_name), novel_name=novel_name)
            tracking_ctx = tracker.get_tracking_context(chapter_number)

            idx = chapter_number - 1
            chapter_plan = state.chapter_plans[idx] if state.chapter_plans and 0 <= idx < len(state.chapter_plans) else {}

            print("  [修订顾问] 正在分析修改意见...")
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
                print("\n已取消选择，退出修订")
                return

            self._execute_revise(state, ch, draft, selected, user_feedback, chapter_plan, tracking_ctx, tracker)
        except Exception as e:
            logger.error(f"Revise error: {e}")
            print(f"\n修订出错：{e}")
            raise

    def _execute_revise(self, state, ch, draft, selected_idea, user_feedback, chapter_plan, tracking_ctx, tracker):
        ch_num = ch.chapter_number
        words_min, words_max = self._get_words_range(state)

        i = ch_num - 1
        completed_summaries = [c.summary for c in state.chapters[:i] if c.summary]
        running_ctx = self.ctx_mgr.build_running_context(
            state.world_data, state.outline, completed_summaries, chapter_plan,
            tracking_context=tracking_ctx,
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
        print("  [作家] 正在根据修改思路修订...")
        revised = self.writer.rewrite(
            draft, feedback, chapter_plan, running_ctx,
            style_guide=state.style_guide,
            words_min=words_min, words_max=words_max,
        )

        if self._interrupted:
            print("  已中断，修订未保存")
            return

        # Step 2: Review
        print("  [审核] 正在审核修订版本...")
        review = self.reviewer.run(
            revised, chapter_plan, state.world_data,
            style_guide=state.style_guide,
            tracking_context=tracking_ctx,
        )

        if self._interrupted:
            print("  已中断，修订未保存")
            return

        # Step 3: Retry once if major issues
        if not review.get("approved", False):
            major = [iss for iss in review.get("issues", []) if iss.get("severity") == "major"]
            if major:
                print(f"  [审核] 发现 {len(major)} 个主要问题，再次修订...")
                additional = "\n".join(
                    f"- [{iss.get('severity')}] {iss.get('description')} → {iss.get('suggestion')}"
                    for iss in review.get("issues", [])
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
            print("  已中断，修订未保存")
            return

        # Step 4: Editor polish
        print("  [编辑] 正在润色修订版本...")
        prev_ending, next_opening = self._get_adjacent_text(state, ch_num)
        final_text = self.editor.run(
            revised, ch_num, prev_ending, next_opening,
            style_guide=state.style_guide,
            tracking_context=tracking_ctx,
        )

        # Step 5: User confirmation
        print(f"\n修订完成，字数变化：{len(draft)} → {len(final_text)}")
        try:
            confirm = input("是否接受此次修订？(y/n)：").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\n  已中断，修订未保存")
            return

        if confirm != "y":
            print("  已放弃修订，保留原版本")
            return

        # Programmatic fixes on revised text
        fixed = False
        fix_result = tracker.auto_fix(final_text, ch_num)
        if fix_result["fixes"]["applied"]:
            final_text = fix_result["text"]
            fixed = True
            print(f"  [追踪] 自动修正角色名：{fix_result['fixes']['applied']}")

        fixed_draft, banned_changes = tracker.auto_fix_banned_words(final_text, state.style_guide)
        if banned_changes:
            final_text = fixed_draft
            fixed = True
            print(f"  [禁用词] 自动修正 {len(banned_changes)} 处：{banned_changes[:5]}")

        cliche_issues = tracker.check_cliches(final_text)
        if cliche_issues:
            print(f"  [陈词滥调] 发现 {len(cliche_issues)} 处：{cliche_issues[:3]}")

        sentence_issues = tracker.check_sentence_patterns(final_text)
        if sentence_issues:
            print(f"  [句式检查] {sentence_issues[:3]}")

        abstract_issues = tracker.check_abstract_nouns(final_text)
        if abstract_issues:
            print(f"  [抽象名词] 发现 {len(abstract_issues)} 处：{abstract_issues[:5]}")

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

        # Update summary and tracking
        ch.summary = self.ctx_mgr.generate_chapter_summary(final_text, ch_num)
        before = tracker.snapshot()
        tracker.update_tracking(ch_num, final_text, chapter_plan, review=review)
        if review.get("tracking_updates"):
            tracker.update_from_review(ch_num, review)
        after = tracker.snapshot()
        tracker.log_changes_csv(ch_num, before, after, source="revise")

        self.state_mgr.save(state)
        print("  修订已保存")

    def _collect_user_feedback(self) -> str:
        print("请输入修改意见（多行输入，单独输入 END 结束）：")
        lines = []
        while True:
            try:
                line = input()
            except (KeyboardInterrupt, EOFError):
                print()
                break
            stripped = line.strip()
            if stripped == "END":
                break
            lines.append(line)
        return "\n".join(lines).strip()

    def _select_idea(self, ideas: list[dict], user_feedback: str):
        if not ideas:
            print("未能生成修改思路，将直接使用您的意见进行修订。")
            return user_feedback

        print("\n以下是几个具体的修改思路：\n")
        for i, idea in enumerate(ideas, 1):
            print(f"  {i}. {idea.get('title', '思路')}")
            desc = idea.get('description', '')
            print(f"     {desc[:80]}{'...' if len(desc) > 80 else ''}")
            print(f"     预期效果：{idea.get('expected_effect', '')[:60]}")
            notes = idea.get('consistency_notes', '')
            if notes and notes != '无':
                print(f"     一致性提醒：{notes[:60]}")
            print()

        print(f"  0. 不使用以上思路，直接用我的原始意见")

        choice = input("\n请选择（输入编号或直接输入自定义修改方向）：").strip()

        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(ideas):
                selected = ideas[idx - 1]
                print(f"\n已选择：{selected.get('title', '')}")
                return selected
            elif idx == 0:
                return user_feedback
            else:
                print("编号无效，使用原始意见")
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
