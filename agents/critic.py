"""Critic agent: analyze user feedback and generate revision ideas."""

import json
import logging

from agents.base import BaseAgent

logger = logging.getLogger(__name__)


class CriticAgent(BaseAgent):
    PROMPT_TEMPLATE = "critic_system.txt"

    def run(
        self,
        chapter_text: str,
        user_feedback: str,
        chapter_plan: dict,
        world_data: dict | None = None,
        tracking_context: str = "",
        style_guide: dict | None = None,
    ) -> list[dict]:
        system = self.apply_style(self.system_prompt, style_guide)

        parts = [
            f"## 章节正文\n{chapter_text[:8000]}\n",
            f"## 章节剧情计划\n{json.dumps(chapter_plan, ensure_ascii=False, indent=2)}\n",
        ]
        if world_data:
            world_str = json.dumps(world_data, ensure_ascii=False, indent=2)
            if len(world_str) > 2000:
                world_str = world_str[:2000] + "\n...(已截断)"
            parts.append(f"## 世界观数据\n{world_str}\n")
        if tracking_context:
            parts.append(f"## 追踪上下文（角色状态、时间线、关系等）\n{tracking_context[:10000]}\n")

        parts.append(f"## 用户修改意见\n{user_feedback}")

        user_msg = "\n".join(parts)

        logger.info("Critic: generating revision ideas...")
        result = self.llm.chat_json(
            system, user_msg,
            temperature=self._temperature(),
        )

        ideas = result.get("ideas", []) if isinstance(result, dict) else []
        if not ideas:
            logger.warning("Critic: no ideas generated, falling back to raw feedback")
            return [{"title": "直接修改", "description": user_feedback, "scope": "全文", "expected_effect": "按用户意见修改", "consistency_notes": ""}]

        logger.info(f"Critic: generated {len(ideas)} revision ideas")
        return ideas
