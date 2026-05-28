"""Capability extractor (Engine A): quantify Director output into capability matrix."""

import json
import logging

from agents.base import BaseAgent

logger = logging.getLogger(__name__)


class CapabilityExtractor(BaseAgent):
    PROMPT_TEMPLATE = "capability_extract_system.txt"

    def run(self, world_data: dict, characters: list, locations: list,
            style_guide: dict | None = None) -> dict:
        user_msg = (
            f"## 世界观数据\n{json.dumps(world_data, ensure_ascii=False, indent=2)}\n\n"
            f"## 角色列表\n{json.dumps(characters, ensure_ascii=False, indent=2)}\n\n"
            f"## 地点列表\n{json.dumps(locations, ensure_ascii=False, indent=2)}\n\n"
            "请根据以上设定，提取角色能力矩阵、世界规则矩阵和地点约束矩阵。"
        )

        system = self.apply_style(self.system_prompt, style_guide)
        logger.info("CapabilityExtractor: extracting capability matrix...")
        result = self.llm.chat_json(
            system, user_msg, temperature=self._temperature()
        )
        if not isinstance(result, dict):
            logger.error(f"CapabilityExtractor: expected dict, got {type(result).__name__}")
            return {"characters": {}, "world_rules": {}, "locations": {}}

        char_count = len(result.get("characters", {}))
        loc_count = len(result.get("locations", {}))
        rule_count = len(result.get("world_rules", {}).get("social_rules", []))
        logger.info(
            f"CapabilityExtractor: done. "
            f"{char_count} characters, {loc_count} locations, {rule_count} social rules."
        )
        return result
