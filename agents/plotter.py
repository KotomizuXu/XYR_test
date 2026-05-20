"""Plot agent: chapter breakdown and plot points."""

import json
import logging

from agents.base import BaseAgent

logger = logging.getLogger(__name__)


class PlotAgent(BaseAgent):
    PROMPT_TEMPLATE = "plotter_system.txt"

    def run(self, outline: dict, world: dict, num_chapters: int, style_guide: dict | None = None) -> list[dict]:
        user_msg = (
            f"## 世界观设定\n{json.dumps(world, ensure_ascii=False, indent=2)}\n\n"
            f"## 故事大纲\n{json.dumps(outline, ensure_ascii=False, indent=2)}\n\n"
            f"## 要求\n"
            f"请将故事拆分为 {num_chapters} 个章节，为每章生成详细的剧情计划。"
        )
        system = self.apply_style(self.system_prompt, style_guide)
        logger.info(f"Plotter: generating {num_chapters} chapter plans...")
        result = self.llm.chat_json(
            system, user_msg, temperature=self._temperature()
        )
        if isinstance(result, dict) and "chapters" in result:
            result = result["chapters"]
        if not isinstance(result, list):
            raise ValueError(f"Plotter returned unexpected format: {type(result)}")
        logger.info(f"Plotter: done. {len(result)} chapters planned.")
        return result
