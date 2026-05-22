"""Long context management via chapter summaries and tracking data."""

import json
import logging

logger = logging.getLogger(__name__)

SUMMARY_PROMPT = """请为以下小说章节生成一份简洁的摘要，包含：
1. 关键事件（2-3句）
2. 角色变化（如有）
3. 重要伏笔或悬念（如有）

摘要字数控制在{max_length}字以内。

章节内容：
{chapter_text}"""

CONTEXT_TEMPLATE = """## 用户原始需求
{story_idea}

## 世界观与角色参考
{world_ref}

## 故事主线
{outline_ref}

## 前文摘要
{summaries}

## 当前章节剧情要点
{current_plan}"""

FULL_CONTEXT_TEMPLATE = """## 用户原始需求
{story_idea}

## 世界观与角色参考
{world_ref}

## 故事主线
{outline_ref}

## 前文摘要
{summaries}

## 追踪数据
{tracking_context}

## 当前章节剧情要点
{current_plan}"""

# Rough char budget: leave room for output within 128K context
# Chinese ~1.5 token/char on average
MAX_CONTEXT_CHARS = 80000


class ContextManager:
    def __init__(self, llm_client, config: dict):
        self.llm = llm_client
        self.max_summary_length = config["novel"]["summary_max_length"]

    def generate_chapter_summary(self, chapter_text: str, chapter_number: int) -> str:
        # 取首尾各3000字，保留章节开头和结尾的关键信息
        if len(chapter_text) > 6000:
            excerpt = chapter_text[:3000] + "\n…（中间省略）…\n" + chapter_text[-3000:]
        else:
            excerpt = chapter_text
        prompt = SUMMARY_PROMPT.format(
            max_length=self.max_summary_length,
            chapter_text=excerpt,
        )
        system = f"你是一个小说编辑助手，擅长提炼故事要点。正在为第{chapter_number}章生成摘要。"
        summary = self.llm.chat(system, prompt, temperature=0.3)
        logger.info(f"Generated summary for chapter {chapter_number}: {summary[:100]}...")
        return summary.strip()

    def build_running_context(
        self,
        world_data: dict | None,
        outline: dict | None,
        completed_summaries: list[str],
        current_chapter_plan: dict,
        tracking_context: str = "",
        story_idea: str = "",
        volumes: list | None = None,
    ) -> str:
        world_ref = self._condense_world(world_data)
        outline_ref = self._condense_outline(outline)
        summaries_text = self._format_summaries(completed_summaries)
        current_plan = self._format_chapter_plan(current_chapter_plan)
        idea_text = story_idea.replace("\n", " ")[:1000] if story_idea else "（无）"

        volume_info = self._format_volume_info(volumes, current_chapter_plan.get("chapter_number", 0))

        if tracking_context:
            result = FULL_CONTEXT_TEMPLATE.format(
                story_idea=idea_text,
                world_ref=world_ref,
                outline_ref=outline_ref,
                summaries=summaries_text,
                tracking_context=tracking_context,
                current_plan=current_plan,
            )
        else:
            result = CONTEXT_TEMPLATE.format(
                story_idea=idea_text,
                world_ref=world_ref,
                outline_ref=outline_ref,
                summaries=summaries_text,
                current_plan=current_plan,
            )

        if volume_info:
            result = volume_info + "\n\n" + result

        # Truncate if context exceeds budget
        if len(result) > MAX_CONTEXT_CHARS:
            logger.warning(f"Context too long ({len(result)} chars), truncating summaries")
            result = self._truncate_context(result, completed_summaries, world_ref, outline_ref, tracking_context, current_chapter_plan, story_idea)

        return result

    def _truncate_context(self, result: str, summaries: list[str], world_ref: str, outline_ref: str, tracking_context: str, current_plan: dict, story_idea: str = "") -> str:
        # Cap tracking context to prevent it from consuming entire budget
        if len(tracking_context) > 10000:
            tracking_context = tracking_context[:10000] + "\n...(追踪数据已截断)"

        # Tiered compression: keep last 3 full, compress 4-10, drop oldest
        total = len(summaries)
        fixed_len = len(world_ref) + len(outline_ref) + len(tracking_context) + 500
        budget = MAX_CONTEXT_CHARS - fixed_len

        # Track how many were originally included before truncation
        tier2_count = min(max(0, total - 3), 7)  # max 7 condensed
        tier1_count = min(3, total)
        originally_included = tier1_count + tier2_count

        kept_lines = []

        # Tier 2: chapters 4-10 from end — one-sentence condensed (drop first)
        tier2 = summaries[max(0, total - 10): max(0, total - 3)]
        tier2_start = max(0, total - 10) + 1
        for idx, s in enumerate(tier2, tier2_start):
            short = s[:100] + "…" if len(s) > 100 else s
            kept_lines.append(f"第{idx}章（简）：{short}")

        # Tier 1: last 3 chapters — full summary
        tier1 = summaries[-3:] if total >= 3 else summaries
        tier1_start = total - len(tier1) + 1
        for idx, s in enumerate(tier1, tier1_start):
            kept_lines.append(f"第{idx}章摘要：{s}")

        # Check budget; pop(0) removes tier2 (older) first, protecting tier1 (newest)
        while kept_lines and sum(len(l) for l in kept_lines) + fixed_len > MAX_CONTEXT_CHARS:
            kept_lines.pop(0)

        kept_count = len(kept_lines)
        dropped = originally_included - kept_count
        if dropped > 0:
            kept_lines.insert(0, f"（前{dropped}章摘要已省略）")

        summaries_text = "\n\n".join(kept_lines)
        current_plan_text = self._format_chapter_plan(current_plan)
        idea_text = story_idea.replace("\n", " ")[:1000] if story_idea else "（无）"

        if tracking_context:
            return FULL_CONTEXT_TEMPLATE.format(
                story_idea=idea_text,
                world_ref=world_ref,
                outline_ref=outline_ref,
                summaries=summaries_text,
                tracking_context=tracking_context,
                current_plan=current_plan_text,
            )
        return CONTEXT_TEMPLATE.format(
            story_idea=idea_text,
            world_ref=world_ref,
            outline_ref=outline_ref,
            summaries=summaries_text,
            current_plan=current_plan_text,
        )

    def _format_volume_info(self, volumes: list | None, chapter_number: int) -> str:
        if not volumes or not chapter_number:
            return ""
        for vol in volumes:
            if vol.start_chapter <= chapter_number <= vol.end_chapter:
                pos = chapter_number - vol.start_chapter + 1
                total = vol.end_chapter - vol.start_chapter + 1
                lines = [f"## 当前卷信息\n第{vol.number}卷「{vol.title}」（第{vol.start_chapter}章-第{vol.end_chapter}章）。本章是本卷第{pos}章/共{total}章。"]
                if chapter_number == vol.end_chapter:
                    lines.append("本章是本卷的最后一章，请给出有分量的卷末收束。")
                return "\n".join(lines)
        return ""

    def _condense_world(self, world_data: dict | None) -> str:
        if not world_data:
            return "（暂无）"
        lines = []
        if "name" in world_data:
            lines.append(f"世界观：{world_data['name']}")
        if "tone" in world_data:
            lines.append(f"整体基调：{world_data['tone']}")
        if "setting" in world_data:
            lines.append(f"背景：{world_data['setting']}")
        if "narrative_perspective" in world_data:
            lines.append(f"叙事视角：{world_data['narrative_perspective']}")
        if "unique_elements" in world_data:
            elements = world_data["unique_elements"]
            if isinstance(elements, list) and elements:
                lines.append(f"世界特色：{'；'.join(str(e) for e in elements[:8])}")
        if "rules" in world_data:
            lines.append(f"世界规则：{world_data['rules']}")
        if "social_structure" in world_data:
            ss = world_data["social_structure"]
            if isinstance(ss, dict):
                parts = []
                for k in ("political_system", "economy", "social_classes", "culture"):
                    if ss.get(k):
                        parts.append(str(ss[k]))
                if parts:
                    lines.append(f"社会结构：{'；'.join(parts)}")
        if "geography" in world_data:
            geo = world_data["geography"]
            if isinstance(geo, dict):
                locs = geo.get("main_locations", [])
                if locs:
                    loc_names = [l.get("name", str(l)) if isinstance(l, dict) else str(l) for l in locs[:8]]
                    lines.append(f"主要地点：{'、'.join(loc_names)}")
        if "factions" in world_data:
            factions = world_data["factions"]
            if isinstance(factions, list) and factions:
                names = [f.get("name", str(f)) if isinstance(f, dict) else str(f) for f in factions[:8]]
                lines.append(f"势力：{'、'.join(names)}")
        if "history" in world_data:
            history = world_data["history"]
            if isinstance(history, list) and history:
                events = [h.get("event", str(h)) if isinstance(h, dict) else str(h) for h in history[:5]]
                lines.append(f"重要历史事件：{'；'.join(events)}")
        if "daily_life" in world_data:
            dl = world_data["daily_life"]
            if isinstance(dl, dict):
                parts = [f"{k}：{v}" for k, v in dl.items() if v]
                if parts:
                    lines.append(f"日常生活：{'；'.join(parts[:6])}")
        if "characters" in world_data:
            chars = world_data["characters"]
            if isinstance(chars, list):
                lines.append("角色：")
                for c in chars[:12]:
                    name = c.get("name", "")
                    role = c.get("role", "")
                    desc = c.get("description", c.get("personality", ""))
                    role_prefix = f"（{role}）" if role else ""
                    bg_parts = []
                    bg = c.get("background", {})
                    if isinstance(bg, dict):
                        for bk, bv in bg.items():
                            if bv:
                                bg_parts.append(f"{bk}：{bv}")
                    bg_str = f" [背景：{'；'.join(bg_parts)}]" if bg_parts else ""
                    lines.append(f"  - {name}{role_prefix}：{desc}{bg_str}")
        return "\n".join(lines) if lines else str(world_data)

    def _condense_outline(self, outline: dict | None) -> str:
        if not outline:
            return "（暂无）"
        lines = []
        if "theme" in outline:
            lines.append(f"主题：{outline['theme']}")
        if "three_act" in outline:
            for act_name, act_desc in outline["three_act"].items():
                lines.append(f"{act_name}：{act_desc}")
        if "ending" in outline:
            lines.append(f"结局方向：{outline['ending']}")
        if "key_turning_points" in outline:
            points = outline["key_turning_points"]
            if points:
                lines.append("关键转折点：" + "；".join(str(p) for p in points))
        return "\n".join(lines) if lines else str(outline)

    def _format_summaries(self, summaries: list[str]) -> str:
        if not summaries:
            return "（这是第一章）"
        parts = []
        for i, s in enumerate(summaries, 1):
            parts.append(f"第{i}章摘要：{s}")
        return "\n\n".join(parts)

    def _format_chapter_plan(self, plan: dict) -> str:
        lines = [f"章节标题：{plan.get('title', '未定')}"]
        if "summary" in plan:
            lines.append(f"概要：{plan['summary']}")
        if "plot_points" in plan:
            lines.append("剧情要点：")
            for pp in plan["plot_points"]:
                lines.append(f"  - {pp}")
        if "emotional_arc" in plan:
            lines.append(f"情绪线：{plan['emotional_arc']}")
        if "emotional_type" in plan:
            lines.append(f"情绪类型：{plan['emotional_type']}")
        if "emotional_intensity" in plan:
            lines.append(f"情绪强度：{plan['emotional_intensity']}")
        if "characters_involved" in plan:
            lines.append(f"出场角色：{', '.join(plan['characters_involved'])}")
        if "foreshadowing" in plan:
            lines.append("伏笔：")
            for fs in plan["foreshadowing"]:
                if isinstance(fs, dict):
                    lines.append(f"  - {fs.get('content', fs)}（可见性：{fs.get('visibility', '?')}，计划回收：第{fs.get('planned_reveal', '?')}章）")
                else:
                    lines.append(f"  - {fs}")
        if "active_plotlines" in plan:
            lines.append(f"活跃线索：{', '.join(plan['active_plotlines'])}")
        if "act" in plan:
            lines.append(f"所属幕：{plan['act']}")
        if "cliffhanger" in plan:
            lines.append(f"章节钩子：{plan['cliffhanger']}")
        if "scene_structure" in plan:
            lines.append(f"场景结构：{plan['scene_structure']}")
        if "tension_level" in plan:
            lines.append(f"张力等级：{plan['tension_level']}")
        if "location" in plan:
            lines.append(f"场景地点：{plan['location']}")
        if "time" in plan:
            lines.append(f"故事时间：{plan['time']}")
        if "previous_link" in plan:
            lines.append(f"承上启下：{plan['previous_link']}")
        if "opening_hook_type" in plan:
            lines.append(f"章首引子类型：{plan['opening_hook_type']}")
        if "ending_hook_type" in plan:
            lines.append(f"章尾悬念类型：{plan['ending_hook_type']}")
        if "characters_on_stage" in plan:
            lines.append(f"实际登场角色：{', '.join(plan['characters_on_stage'])}")
        if "scene_list" in plan and plan["scene_list"]:
            lines.append("场景列表：")
            for scene in plan["scene_list"]:
                if isinstance(scene, dict):
                    lines.append(f"  - {scene.get('name', '?')}（地点：{scene.get('location', '?')}，目的：{scene.get('purpose', '?')}）")
                else:
                    lines.append(f"  - {scene}")
        return "\n".join(lines)
