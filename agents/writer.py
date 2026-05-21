"""Writer agent: draft chapter text."""

import logging

from agents.base import BaseAgent
from core.context_manager import ContextManager

logger = logging.getLogger(__name__)


class WriterAgent(BaseAgent):
    PROMPT_TEMPLATE = "writer_system.txt"

    def __init__(self, llm, config: dict, ctx_mgr: ContextManager):
        super().__init__(llm, config)
        self.ctx_mgr = ctx_mgr

    def _build_system_prompt(self, words_min: int, words_max: int, style_guide: dict | None = None) -> str:
        tone = "根据设定风格"
        perspective = "第三人称有限视角"
        if style_guide:
            tone = style_guide.get("tone", {}).get("overall", tone)
            perspective = style_guide.get("worldbuilding", {}).get("exposition_style", perspective)

        safe_prompt = self.system_prompt.replace("{", "{{").replace("}", "}}")
        safe_prompt = safe_prompt.replace("{{words_min}}", str(words_min))
        safe_prompt = safe_prompt.replace("{{words_max}}", str(words_max))
        safe_prompt = safe_prompt.replace("{{tone_guidance}}", tone)
        safe_prompt = safe_prompt.replace("{{narrative_perspective}}", perspective)

        return self.apply_style(safe_prompt, style_guide)

    def _resolve_words(self, words_min: int | None, words_max: int | None) -> tuple[int, int]:
        cfg = self.config["novel"]["words_per_chapter"]
        return words_min or cfg["min"], words_max or cfg["max"]

    def run(self, chapter_plan: dict, running_context: str, style_guide: dict | None = None, words_min: int | None = None, words_max: int | None = None) -> str:
        words_min, words_max = self._resolve_words(words_min, words_max)
        system = self._build_system_prompt(words_min, words_max, style_guide)

        user_msg = f"{running_context}\n\n请根据以上上下文和剧情要点，撰写本章正文。"
        logger.info(f"Writer: drafting chapter {chapter_plan.get('chapter_number', '?')}...")

        text = self.llm.chat(system, user_msg, temperature=self._temperature())

        # Check word count, request continuation if too short
        char_count = len(text)
        if char_count < words_min * 0.9:
            logger.info(f"Writer: text too short ({char_count} chars), requesting continuation...")
            continuation = self.llm.chat_with_history(
                system,
                [
                    {"role": "user", "content": user_msg},
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": "请继续写，不要重复已写的内容，直接从上文结尾处继续："},
                ],
                temperature=self._temperature(),
                max_tokens=None,
            )
            text = text + continuation

        logger.info(f"Writer: chapter done. {len(text)} chars.")
        return text.strip()

    def rewrite(self, draft: str, review_feedback: str, chapter_plan: dict, running_context: str, style_guide: dict | None = None, words_min: int | None = None, words_max: int | None = None) -> str:
        words_min, words_max = self._resolve_words(words_min, words_max)
        system = self._build_system_prompt(words_min, words_max, style_guide)

        # 重写时不重复传入完整 running_context，只传审稿意见和草稿
        # running_context 已在 system prompt 中通过风格指南体现，避免 token 叠加
        user_msg = (
            f"## 审稿意见\n{review_feedback}\n\n"
            f"## 原始草稿\n{draft}\n\n"
            f"请根据审稿意见修改上述草稿，修复指出的所有问题。保持原有的好内容，只修改有问题的部分。"
        )

        logger.info(f"Writer: rewriting chapter {chapter_plan.get('chapter_number', '?')}...")
        text = self.llm.chat(system, user_msg, temperature=self._temperature())

        # Check word count, request continuation if too short
        char_count = len(text)
        if char_count < words_min * 0.9:
            logger.info(f"Writer: rewrite too short ({char_count} chars), requesting continuation...")
            continuation = self.llm.chat_with_history(
                system,
                [
                    {"role": "user", "content": user_msg},
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": "请继续写，不要重复已写的内容，直接从上文结尾处继续："},
                ],
                temperature=self._temperature(),
                max_tokens=None,
            )
            text = text + continuation

        logger.info(f"Writer: rewrite done. {len(text)} chars.")
        return text.strip()
