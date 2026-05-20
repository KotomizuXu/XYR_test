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

CONTEXT_TEMPLATE = """## 世界观与角色参考
{world_ref}

## 故事主线
{outline_ref}

## 前文摘要
{summaries}

## 当前章节剧情要点
{current_plan}"""

FULL_CONTEXT_TEMPLATE = """## 世界观与角色参考
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
MAX_CONTEXT_CHARS = 60000


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
    ) -> str:
        world_ref = self._condense_world(world_data)
        outline_ref = self._condense_outline(outline)
        summaries_text = self._format_summaries(completed_summaries)
        current_plan = self._format_chapter_plan(current_chapter_plan)

        if tracking_context:
            result = FULL_CONTEXT_TEMPLATE.format(
                world_ref=world_ref,
                outline_ref=outline_ref,
                summaries=summaries_text,
                tracking_context=tracking_context,
                current_plan=current_plan,
            )
        else:
            result = CONTEXT_TEMPLATE.format(
                world_ref=world_ref,
                outline_ref=outline_ref,
                summaries=summaries_text,
                current_plan=current_plan,
            )

        # Truncate if context exceeds budget
        if len(result) > MAX_CONTEXT_CHARS:
            logger.warning(f"Context too long ({len(result)} chars), truncating summaries")
            result = self._truncate_context(result, completed_summaries, world_ref, outline_ref, tracking_context, current_chapter_plan)

        return result

    def _truncate_context(self, result: str, summaries: list[str], world_ref: str, outline_ref: str, tracking_context: str, current_plan: dict) -> str:
        # Tiered compression: keep last 3 full, compress 4-10, drop oldest
        total = len(summaries)
        fixed_len = len(world_ref) + len(outline_ref) + len(tracking_context) + 500
        budget = MAX_CONTEXT_CHARS - fixed_len

        kept_lines = []

        # Tier 1: last 3 chapters — full summary
        tier1 = summaries[-3:] if total >= 3 else summaries
        tier1_start = total - len(tier1) + 1
        for idx, s in enumerate(tier1, tier1_start):
            kept_lines.append(f"第{idx}章摘要：{s}")

        # Tier 2: chapters 4-10 from end — one-sentence condensed
        tier2 = summaries[max(0, total - 10): max(0, total - 3)]
        tier2_start = max(0, total - 10) + 1
        for idx, s in enumerate(tier2, tier2_start):
            short = s[:60] + "…" if len(s) > 60 else s
            kept_lines.append(f"第{idx}章（简）：{short}")

        # Check budget; if still over, drop tier2 entries from oldest
        while kept_lines and sum(len(l) for l in kept_lines) + fixed_len > MAX_CONTEXT_CHARS:
            kept_lines.pop(0)

        dropped = total - len([l for l in kept_lines if "（简）" not in l and "摘要" in l]) - len([l for l in kept_lines if "（简）" in l])
        if dropped > 0:
            kept_lines.insert(0, f"（前{dropped}章摘要已省略）")

        summaries_text = "\n\n".join(kept_lines)
        current_plan_text = self._format_chapter_plan(current_plan)

        if tracking_context:
            return FULL_CONTEXT_TEMPLATE.format(
                world_ref=world_ref,
                outline_ref=outline_ref,
                summaries=summaries_text,
                tracking_context=tracking_context,
                current_plan=current_plan_text,
            )
        return CONTEXT_TEMPLATE.format(
            world_ref=world_ref,
            outline_ref=outline_ref,
            summaries=summaries_text,
            current_plan=current_plan_text,
        )

    def _condense_world(self, world_data: dict | None) -> str:
        if not world_data:
            return "（暂无）"
        lines = []
        if "setting" in world_data:
            lines.append(f"背景：{world_data['setting']}")
        if "characters" in world_data:
            chars = world_data["characters"]
            if isinstance(chars, list):
                for c in chars[:8]:
                    name = c.get("name", "")
                    desc = c.get("description", c.get("personality", ""))
                    lines.append(f"- {name}：{desc}")
        if "rules" in world_data:
            lines.append(f"世界规则：{world_data['rules']}")
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
        if "cliffhanger" in plan:
            lines.append(f"章节钩子：{plan['cliffhanger']}")
        if "scene_structure" in plan:
            lines.append(f"场景结构：{plan['scene_structure']}")
        if "tension_level" in plan:
            lines.append(f"张力等级：{plan['tension_level']}")
        return "\n".join(lines)
