"""Outline auditor (Engine B+C): per-chapter cross-validation + quality scoring."""

import json
import logging

from agents.base import BaseAgent

logger = logging.getLogger(__name__)


class OutlineAuditor(BaseAgent):
    PROMPT_TEMPLATE = "outline_audit_system.txt"

    def run(
        self,
        chapter_plans: list[dict],
        capability_matrix: dict,
        outline: dict,
        style_guide: dict | None = None,
    ) -> list[dict]:
        user_msg = (
            f"## 章节计划（本批次 {len(chapter_plans)} 章）\n"
            f"{json.dumps(chapter_plans, ensure_ascii=False, indent=2)}\n\n"
            f"## 角色能力矩阵\n"
            f"{json.dumps(capability_matrix.get('characters', {}), ensure_ascii=False, indent=2)}\n\n"
            f"## 世界规则矩阵\n"
            f"{json.dumps(capability_matrix.get('world_rules', {}), ensure_ascii=False, indent=2)}\n\n"
            f"## 地点约束矩阵\n"
            f"{json.dumps(capability_matrix.get('locations', {}), ensure_ascii=False, indent=2)}\n\n"
            f"## 故事大纲\n"
            f"{json.dumps(outline, ensure_ascii=False, indent=2)}\n\n"
        )
        if style_guide:
            user_msg += (
                f"## 风格指南（摘要）\n"
                f"{json.dumps(self._summarize_style(style_guide), ensure_ascii=False, indent=2)}\n\n"
            )
        user_msg += "请对以上章节逐一进行交叉校验和质量评分。"

        system = self.apply_style(self.system_prompt, style_guide)
        ch_range = f"{chapter_plans[0].get('chapter_number', '?')}-{chapter_plans[-1].get('chapter_number', '?')}"
        logger.info(f"OutlineAuditor: auditing chapters {ch_range}...")
        result = self.llm.chat_json(
            system, user_msg, temperature=self._temperature()
        )
        if not isinstance(result, list):
            logger.error(f"OutlineAuditor: expected list, got {type(result).__name__}")
            return []

        approved_count = sum(1 for r in result if r.get("approved"))
        issue_count = sum(len(r.get("issues", [])) for r in result)
        logger.info(
            f"OutlineAuditor: done. {approved_count}/{len(result)} approved, "
            f"{issue_count} total issues."
        )
        return result

    @staticmethod
    def _summarize_style(style_guide: dict) -> dict:
        """提取风格指南中与大纲审核相关的字段，减小 prompt 体积。"""
        return {
            "pacing": style_guide.get("pacing", {}),
            "setting": style_guide.get("setting", {}),
            "style_presets": style_guide.get("style_presets", {}),
        }
