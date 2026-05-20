"""Style advisor agent: generates style guide from user description."""

import logging

from agents.base import BaseAgent

logger = logging.getLogger(__name__)


class StyleAdvisorAgent(BaseAgent):
    PROMPT_TEMPLATE = "style_advisor_system.txt"

    def run(self, style_description: str, story_idea: str | None = None) -> dict:
        user_msg = f"用户期望的小说风格：{style_description}\n\n"
        if story_idea:
            user_msg += f"故事灵感：{story_idea}\n\n"
        user_msg += "请根据以上信息，生成完整的风格指南。注意 suggestions 中的参数建议要匹配故事的实际体量（如短篇、中篇、长篇）。"
        logger.info(f"StyleAdvisor: generating style guide for '{style_description[:50]}...'")
        result = self.llm.chat_json(
            self.system_prompt, user_msg, temperature=self._temperature()
        )
        if not isinstance(result, dict):
            logger.error(f"StyleAdvisor: expected dict, got {type(result).__name__}")
            return {}
        logger.info(f"StyleAdvisor: done. Style name: {result.get('style_name', '?')}")
        return result
