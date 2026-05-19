"""Style advisor agent: generates style guide from user description."""

import logging

from agents.base import BaseAgent

logger = logging.getLogger(__name__)


class StyleAdvisorAgent(BaseAgent):
    PROMPT_TEMPLATE = "style_advisor_system.txt"

    def run(self, style_description: str) -> dict:
        user_msg = (
            f"用户期望的小说风格：{style_description}\n\n"
            f"请根据以上描述，生成完整的风格指南。"
        )
        logger.info(f"StyleAdvisor: generating style guide for '{style_description[:50]}...'")
        result = self.llm.chat_json(
            self.system_prompt, user_msg, temperature=0.5, max_tokens=4096
        )
        logger.info(f"StyleAdvisor: done. Style name: {result.get('style_name', '?')}")
        return result
