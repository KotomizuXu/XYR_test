"""Director agent: world-building, character design, and outline."""

import json
import logging

from agents.base import BaseAgent

logger = logging.getLogger(__name__)


class DirectorAgent(BaseAgent):
    PROMPT_TEMPLATE = "director_system.txt"

    def run(self, story_idea: str, num_chapters: int = 20, style_guide: dict | None = None) -> dict:
        user_msg = (
            f"故事灵感：{story_idea}\n\n"
            f"计划章节数：{num_chapters}章\n\n"
            f"请根据以上灵感，生成完整的小说设定。"
        )
        system = self.apply_style(self.system_prompt, style_guide)
        logger.info("Director: generating world and outline...")
        result = self.llm.chat_json(
            system, user_msg, temperature=self._temperature()
        )
        if not isinstance(result, dict):
            logger.error(f"Director: expected dict from chat_json, got {type(result).__name__}")
            return {}
        logger.info(f"Director: done. Characters: {len(result.get('characters', []))}")
        return result
