"""Director agent: world-building, character design, and outline."""

import json
import logging

from agents.base import BaseAgent

logger = logging.getLogger(__name__)


class DirectorAgent(BaseAgent):
    PROMPT_TEMPLATE = "director_system.txt"

    def run(self, story_idea: str, num_chapters: int = 20) -> dict:
        user_msg = (
            f"故事灵感：{story_idea}\n\n"
            f"计划章节数：{num_chapters}章\n\n"
            f"请根据以上灵感，生成完整的小说设定。"
        )
        logger.info("Director: generating world and outline...")
        result = self.llm.chat_json(
            self.system_prompt, user_msg, temperature=self._temperature(), max_tokens=8192
        )
        logger.info(f"Director: done. Characters: {len(result.get('characters', []))}")
        return result
