"""Outline global checker (Engine D): batch-level + global-level checks."""

import json
import logging

from agents.base import BaseAgent

logger = logging.getLogger(__name__)


class OutlineGlobalChecker(BaseAgent):
    PROMPT_TEMPLATE = "outline_global_check_system.txt"

    def run(self, **kwargs) -> dict:
        """BaseAgent 抽象方法实现：默认走全局检查。"""
        return self.run_global(**kwargs)

    def run_batch(
        self,
        chapter_plans: list[dict],
        capability_matrix: dict,
        outline: dict,
        style_guide: dict | None = None,
        thresholds: dict | None = None,
    ) -> dict:
        """批次级检查（D1 遗忘曲线 + D2 节奏曲线）。"""
        return self._run(
            scope="batch",
            chapter_plans=chapter_plans,
            capability_matrix=capability_matrix,
            outline=outline,
            style_guide=style_guide,
            thresholds=thresholds,
        )

    def run_global(
        self,
        chapter_plans: list[dict],
        capability_matrix: dict,
        outline: dict,
        style_guide: dict | None = None,
        thresholds: dict | None = None,
    ) -> dict:
        """全局级检查（D1-D4 全部）。"""
        return self._run(
            scope="global",
            chapter_plans=chapter_plans,
            capability_matrix=capability_matrix,
            outline=outline,
            style_guide=style_guide,
            thresholds=thresholds,
        )

    def _run(
        self,
        scope: str,
        chapter_plans: list[dict],
        capability_matrix: dict,
        outline: dict,
        style_guide: dict | None,
        thresholds: dict | None,
    ) -> dict:
        # 批次模式下只传本批次章节；全局模式下传全部章节
        user_msg = (
            f"## 审计范围\nscope={scope}\n\n"
            f"## 章节计划（共 {len(chapter_plans)} 章）\n"
            f"{json.dumps(chapter_plans, ensure_ascii=False, indent=2)}\n\n"
            f"## 角色能力矩阵\n"
            f"{json.dumps(capability_matrix, ensure_ascii=False, indent=2)}\n\n"
            f"## 故事大纲\n"
            f"{json.dumps(outline, ensure_ascii=False, indent=2)}\n\n"
        )
        if style_guide:
            user_msg += (
                f"## 风格指南（摘要）\n"
                f"{json.dumps(self._summarize_style(style_guide), ensure_ascii=False, indent=2)}\n\n"
            )
        if thresholds:
            user_msg += (
                f"## 遗忘检测阈值\n"
                f"{json.dumps(thresholds, ensure_ascii=False, indent=2)}\n\n"
            )
        user_msg += f"请执行 {scope} 级别的全局检查。"

        system = self.apply_style(self.system_prompt, style_guide)
        logger.info(f"OutlineGlobalChecker: running {scope} check on {len(chapter_plans)} chapters...")
        result = self.llm.chat_json(
            system, user_msg, temperature=self._temperature()
        )
        if not isinstance(result, dict):
            logger.error(f"OutlineGlobalChecker: expected dict, got {type(result).__name__}")
            return {"scope": scope, "forgotten_elements": {}, "pacing_curve": {},
                    "completeness": {}, "cross_batch_issues": []}

        forgotten = result.get("forgotten_elements", {})
        f_count = (
            len(forgotten.get("characters", []))
            + len(forgotten.get("plotlines", []))
            + len(forgotten.get("foreshadowing", []))
        )
        pacing_warnings = len(result.get("pacing_curve", {}).get("warnings", []))
        logger.info(
            f"OutlineGlobalChecker ({scope}): done. "
            f"{f_count} forgotten elements, {pacing_warnings} pacing warnings."
        )
        return result

    @staticmethod
    def _summarize_style(style_guide: dict) -> dict:
        return {
            "pacing": style_guide.get("pacing", {}),
            "setting": style_guide.get("setting", {}),
        }
