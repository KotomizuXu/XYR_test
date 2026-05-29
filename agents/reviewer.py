"""Reviewer agent: check chapter quality and consistency."""

import json
import logging

from agents.base import BaseAgent

logger = logging.getLogger(__name__)


class ReviewerAgent(BaseAgent):
    PROMPT_TEMPLATE = "reviewer_system.txt"

    def run(self, chapter_text: str, chapter_plan: dict, world_data: dict | None = None, style_guide: dict | None = None, tracking_context: str = "") -> dict:
        user_msg = (
            f"## 章节剧情计划\n{json.dumps(chapter_plan, ensure_ascii=False, indent=2)}\n\n"
            f"## 章节正文\n{chapter_text}\n\n"
        )
        if world_data:
            world_str = json.dumps(world_data, ensure_ascii=False, indent=2)
            if len(world_str) > 2000:
                world_str = world_str[:2000] + "\n...(已截断)"
            user_msg += f"## 世界观参考\n{world_str}\n\n"
        if tracking_context:
            user_msg += f"## 追踪数据（请交叉校验一致性）\n{tracking_context}\n\n"

        user_msg += "请审核以上章节内容，特别注意角色一致性、时间线逻辑和世界观规则。"

        system = self.apply_style(self.system_prompt, style_guide)
        logger.info(f"Reviewer: checking chapter {chapter_plan.get('chapter_number', '?')}...")
        result = self.llm.chat_json(
            system, user_msg, temperature=self._temperature()
        )
        if not isinstance(result, dict):
            if isinstance(result, list) and result and isinstance(result[0], dict):
                logger.warning(f"Reviewer: got list from chat_json, extracting first element")
                result = result[0]
            else:
                logger.error(f"Reviewer: expected dict from chat_json, got {type(result).__name__}: {str(result)[:200]}")
                return {"approved": False, "issues": [{"severity": "major", "description": "审校结果解析异常（LLM 返回格式错误），请重新审核",
                    "suggestion": "重新提交审核请求"}], "consistency_checks": {}, "overall_quality": 0,
                    "strengths": [], "auto_fix_suggestions": [], "tracking_updates": {}}

        approved = result.get("approved", False)
        quality = result.get("overall_quality", 0)
        issues = result.get("issues", [])
        major_count = sum(1 for i in issues if i.get("severity") == "major")
        consistency = result.get("consistency_checks", {})

        logger.info(f"Reviewer: approved={approved}, quality={quality}, issues={len(issues)} (major={major_count}), consistency={consistency}")
        return result
