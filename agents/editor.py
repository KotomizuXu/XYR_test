"""Editor agent: polish and refine chapter text."""

import logging

from agents.base import BaseAgent

logger = logging.getLogger(__name__)


class EditorAgent(BaseAgent):
    PROMPT_TEMPLATE = "editor_system.txt"

    def run(
        self,
        chapter_text: str,
        chapter_number: int,
        prev_chapter_ending: str = "",
        next_chapter_opening: str = "",
        style_guide: dict | None = None,
        tracking_context: str = "",
    ) -> str:
        user_msg = f"## 第{chapter_number}章正文\n{chapter_text}\n\n"
        if prev_chapter_ending:
            user_msg += f"## 上一章结尾（参考衔接）\n{prev_chapter_ending[-500:]}\n\n"
        if next_chapter_opening:
            user_msg += f"## 下一章开头（参考衔接）\n{next_chapter_opening[:500:]}\n\n"
        if tracking_context:
            user_msg += f"## 追踪数据（润色时保持一致性）\n{tracking_context}\n\n"
        user_msg += "请对以上章节进行润色编辑。"

        system = self.apply_style(self.system_prompt, style_guide)
        logger.info(f"Editor: polishing chapter {chapter_number}...")
        result = self.llm.chat(
            system, user_msg, temperature=self._temperature(), max_tokens=32768
        )
        logger.info(f"Editor: done. {len(result)} chars.")
        return result.strip()
