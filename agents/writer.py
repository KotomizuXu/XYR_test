"""Writer agent: draft chapter text."""

import json
import logging
import re

from agents.base import BaseAgent
from core.context_manager import ContextManager

logger = logging.getLogger(__name__)


def _count_chinese_chars(text: str) -> int:
    """统计中文字符数（排除 Markdown 标记和标点）。I1。

    与 chinese-novelist-skill/scripts/check_chapter_wordcount.py 的算法一致：
    先剥离 Markdown 修饰，再统计 \\u4e00-\\u9fff 范围内的汉字数量。
    用于字数不足续写判断比 len(text) 更准确——避免被空行 / 标点 / Markdown
    标题撑起的"虚假长度"骗过续写阈值。
    """
    if not text:
        return 0
    # 移除 Markdown 标记（标题、粗体、斜体、删除线、行内代码、链接）
    stripped = re.sub(r'#{1,6}\s*', '', text)
    stripped = re.sub(r'\*\*(.*?)\*\*', r'\1', stripped)
    stripped = re.sub(r'\*(.*?)\*', r'\1', stripped)
    stripped = re.sub(r'~~(.*?)~~', r'\1', stripped)
    stripped = re.sub(r'`(.*?)`', r'\1', stripped)
    stripped = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', stripped)
    return len(re.findall(r'[一-鿿]', stripped))


class WriterAgent(BaseAgent):
    PROMPT_TEMPLATE = "writer_system.txt"

    def __init__(self, llm, config: dict, ctx_mgr: ContextManager):
        super().__init__(llm, config)
        self.ctx_mgr = ctx_mgr
        ctx_cfg = config.get("context_budget", {}) or {}
        self.rewrite_ctx_cap = ctx_cfg.get("rewrite_ctx_cap", 8000)
        self.continuation_tail_chars = ctx_cfg.get("continuation_tail_chars", 2000)

    def _build_system_prompt(self, words_min: int, words_max: int, style_guide: dict | None = None, is_rewrite: bool = False) -> str:
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

        prompt = self.apply_style(safe_prompt, style_guide)
        if is_rewrite:
            prompt += (
                "\n\n## 重写专项要求\n"
                "本次是基于审稿意见的修订，请实质性改写被指出问题的段落（不是字面微调或同义替换），"
                "同时严格保留 strengths 列表中标注的优秀内容。如审稿指出\"对话单调\"，需重新设计对话表达；"
                "如指出\"节奏拖沓\"，需砍掉冗余段落而不是仅仅压缩描写。"
            )
        return prompt

    def _resolve_words(self, words_min: int | None, words_max: int | None) -> tuple[int, int]:
        cfg = self.config["novel"]["words_per_chapter"]
        return words_min or cfg["min"], words_max or cfg["max"]

    def run(self, chapter_plan: dict, running_context: str, style_guide: dict | None = None, words_min: int | None = None, words_max: int | None = None) -> str:
        words_min, words_max = self._resolve_words(words_min, words_max)
        system = self._build_system_prompt(words_min, words_max, style_guide)

        user_msg = f"{running_context}\n\n请根据以上上下文和剧情要点，撰写本章正文。"
        logger.info(f"Writer: drafting chapter {chapter_plan.get('chapter_number', '?')}...")

        text = self.llm.chat(system, user_msg, temperature=self._temperature())

        # Check word count, request continuation if too short (I1: 仅统计中文字数)
        char_count = _count_chinese_chars(text)
        if char_count < words_min * 0.9:
            logger.info(f"Writer: text too short ({char_count} 中文字), requesting continuation...")
            # 续写时只回传 plan 锚点 + 草稿尾部，避免再次叠加 running_context 溢出
            plan_anchor = self._plan_anchor(chapter_plan)
            tail = text[-self.continuation_tail_chars:] if len(text) > self.continuation_tail_chars else text
            continuation = self.llm.chat_with_history(
                system,
                [
                    {"role": "user", "content": plan_anchor},
                    {"role": "assistant", "content": tail},
                    {"role": "user", "content": "请直接从上文结尾处继续写下去，不要重复已写内容，不要回顾前文："},
                ],
                temperature=self._temperature(),
                max_tokens=None,
            )
            text = text + continuation

        logger.info(f"Writer: chapter done. {_count_chinese_chars(text)} 中文字 / {len(text)} 字符。")
        return text.strip()

    @staticmethod
    def _plan_anchor(chapter_plan: dict) -> str:
        """续写时回传的最小锚点：章节标题 + 概要 + 关键剧情点，控制在 1.5K 字以内。"""
        if not chapter_plan:
            return "请继续撰写当前章节正文。"
        lines = [f"章节：第{chapter_plan.get('chapter_number', '?')}章「{chapter_plan.get('title', '')}」"]
        if chapter_plan.get("summary"):
            lines.append(f"概要：{chapter_plan['summary']}")
        plot_points = chapter_plan.get("plot_points") or []
        if plot_points:
            lines.append("剧情要点：")
            for pp in plot_points[:5]:
                lines.append(f"  - {pp}")
        anchor = "\n".join(lines)
        return anchor[:1500]

    def rewrite(self, draft: str, review_feedback: str, chapter_plan: dict, running_context: str, style_guide: dict | None = None, words_min: int | None = None, words_max: int | None = None) -> str:
        words_min, words_max = self._resolve_words(words_min, words_max)
        system = self._build_system_prompt(words_min, words_max, style_guide, is_rewrite=True)

        # 重写时只传精简上下文（rewrite_ctx_cap 默认 8000）：plan + 审稿意见 + 草稿足够
        plan_str = json.dumps(chapter_plan, ensure_ascii=False, indent=2) if chapter_plan else ""
        ctx_cap = self.rewrite_ctx_cap
        condensed_ctx = ""
        if running_context:
            condensed_ctx = running_context[:ctx_cap] + ("\n...(上下文已截断)" if len(running_context) > ctx_cap else "")

        user_msg = ""
        if plan_str:
            user_msg += f"## 章节剧情计划（重写时必须遵循）\n{plan_str}\n\n"
        if condensed_ctx:
            user_msg += f"## 写作上下文\n{condensed_ctx}\n\n"
        user_msg += (
            f"## 审稿意见（必须逐一修复，不能只做表面调整）\n{review_feedback}\n\n"
            f"## 原始草稿\n{draft}\n\n"
            f"## 重写要求\n"
            f"请针对审稿意见中指出的每一个问题进行实质性修改。具体要求：\n"
            f"1. 对 major 级别问题：必须大幅重写相关段落，不能只改几个词\n"
            f"2. 对 warning 级别问题：必须有可感知的改善，不能原样保留\n"
            f"3. 如果审稿指出\"对话单调\"，必须完全重写对话表达和结构\n"
            f"4. 如果审稿指出\"节奏拖沓\"，必须删除冗余段落并加快节奏\n"
            f"5. 如果审稿指出\"角色OOC\"，必须重写该角色全部言行使其符合人设\n"
            f"6. 保留未出问题段落的精华，但出问题的段落宁可重写也不要修修补补\n"
            f"7. 输出完整的修改后章节，不要省略任何部分\n"
        )

        rewrite_temp = min(self._temperature() + 0.25, 0.95)
        logger.info(f"Writer: rewriting chapter {chapter_plan.get('chapter_number', '?')} (temp={rewrite_temp:.2f})...")
        text = self.llm.chat(system, user_msg, temperature=rewrite_temp)

        # Check word count, request continuation if too short (I1: 仅统计中文字数)
        char_count = _count_chinese_chars(text)
        if char_count < words_min * 0.9:
            logger.info(f"Writer: rewrite too short ({char_count} 中文字), requesting continuation...")
            plan_anchor = self._plan_anchor(chapter_plan)
            tail = text[-self.continuation_tail_chars:] if len(text) > self.continuation_tail_chars else text
            continuation = self.llm.chat_with_history(
                system,
                [
                    {"role": "user", "content": plan_anchor},
                    {"role": "assistant", "content": tail},
                    {"role": "user", "content": "请直接从上文结尾处继续写下去，不要重复已写内容，不要回顾前文："},
                ],
                temperature=rewrite_temp,
                max_tokens=None,
            )
            text = text + continuation

        logger.info(f"Writer: rewrite done. {_count_chinese_chars(text)} 中文字 / {len(text)} 字符。")
        return text.strip()
