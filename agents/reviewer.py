"""Reviewer agent: check chapter quality and consistency."""

import json
import logging

from agents.base import BaseAgent

logger = logging.getLogger(__name__)


class ReviewerAgent(BaseAgent):
    PROMPT_TEMPLATE = "reviewer_system.txt"

    def run(self, chapter_text: str, chapter_plan: dict, world_data: dict | None = None) -> dict:
        user_msg = (
            f"## 章节剧情计划\n{json.dumps(chapter_plan, ensure_ascii=False, indent=2)}\n\n"
            f"## 章节正文\n{chapter_text}\n\n"
        )
        if world_data:
            user_msg += f"## 世界观参考\n{json.dumps(world_data, ensure_ascii=False, indent=2)[:2000]}\n\n"

        user_msg += "请审核以上章节内容。"

        logger.info(f"Reviewer: checking chapter {chapter_plan.get('chapter_number', '?')}...")
        result = self.llm.chat_json(
            self.system_prompt, user_msg, temperature=self._temperature(), max_tokens=4096
        )

        approved = result.get("approved", False)
        quality = result.get("overall_quality", 0)
        issues = result.get("issues", [])
        major_count = sum(1 for i in issues if i.get("severity") == "major")

        logger.info(f"Reviewer: approved={approved}, quality={quality}, issues={len(issues)} (major={major_count})")
        return result
