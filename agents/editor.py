"""Editor agent: polish and refine chapter text."""

import logging

from agents.base import BaseAgent
from core.context_manager import ContextManager

logger = logging.getLogger(__name__)


class EditorAgent(BaseAgent):
    PROMPT_TEMPLATE = "editor_system.txt"

    def __init__(self, llm, config: dict, ctx_mgr: ContextManager):
        super().__init__(llm, config)
        self.ctx_mgr = ctx_mgr

    def run(
        self,
        chapter_text: str,
        chapter_number: int,
        prev_chapter_ending: str = "",
        next_chapter_opening: str = "",
        style_guide: dict | None = None,
    ) -> str:
        user_msg = f"## 第{chapter_number}章正文\n{chapter_text}\n\n"
        if prev_chapter_ending:
            user_msg += f"## 上一章结尾（参考衔接）\n{prev_chapter_ending[-500:]}\n\n"
        if next_chapter_opening:
            user_msg += f"## 下一章开头（参考衔接）\n{next_chapter_opening[:500]}\n\n"
        user_msg += "请对以上章节进行润色编辑。"

        system = self.apply_style(self.system_prompt, style_guide)
        logger.info(f"Editor: polishing chapter {chapter_number}...")
        result = self.llm.chat(
            system, user_msg, temperature=self._temperature(), max_tokens=8192
        )
        logger.info(f"Editor: done. {len(result)} chars.")
        return result.strip()
