"""Plot agent: chapter breakdown and plot points."""

import json
import logging

from core import ui

from agents.base import BaseAgent

logger = logging.getLogger(__name__)

BATCH_SIZE = 5


class PlotAgent(BaseAgent):
    PROMPT_TEMPLATE = "plotter_system.txt"

    def run(self, outline: dict, world: dict, num_chapters: int, style_guide: dict | None = None) -> list[dict]:
        system = self.apply_style(self.system_prompt, style_guide)
        world_str = json.dumps(world, ensure_ascii=False, indent=2)
        outline_str = json.dumps(outline, ensure_ascii=False, indent=2)

        if num_chapters <= BATCH_SIZE:
            return self._generate_batch(system, world_str, outline_str, 1, num_chapters, num_chapters)

        all_plans: list[dict] = []
        for start in range(1, num_chapters + 1, BATCH_SIZE):
            end = min(start + BATCH_SIZE - 1, num_chapters)
            batch_num = (start - 1) // BATCH_SIZE + 1
            total_batches = (num_chapters + BATCH_SIZE - 1) // BATCH_SIZE
            ui.info(f"[编剧] 生成第 {start}-{end} 章计划（{batch_num}/{total_batches}）...")
            existing_summaries = ""
            if all_plans:
                summaries = [
                    f"第{p['chapter_number']}章「{p.get('title', '')}」：{p.get('summary', '')}"
                    for p in all_plans
                ]
                existing_summaries = (
                    "\n\n## 已规划的章节摘要（请保持连贯）\n"
                    + "\n".join(f"- {s}" for s in summaries)
                )
            batch = self._generate_batch(
                system, world_str, outline_str, start, end, num_chapters,
                existing_summaries=existing_summaries,
            )
            all_plans.extend(batch)

        logger.info(f"Plotter: done. {len(all_plans)} chapters planned.")
        return all_plans

    def _generate_batch(
        self, system: str, world_str: str, outline_str: str,
        start: int, end: int, total: int,
        existing_summaries: str = "",
    ) -> list[dict]:
        user_msg = (
            f"## 世界观设定\n{world_str}\n\n"
            f"## 故事大纲\n{outline_str}\n"
            f"{existing_summaries}\n\n"
            f"## 要求\n"
            f"请仅为第 {start} 到第 {end} 章（共 {total} 章）生成章节计划。"
        )
        logger.info(f"Plotter: generating chapters {start}-{end} of {total}...")
        result = self.llm.chat_json(
            system, user_msg, temperature=self._temperature()
        )
        if isinstance(result, dict) and "chapters" in result:
            result = result["chapters"]
        if not isinstance(result, list):
            raise ValueError(f"Plotter returned unexpected format: {type(result)}")
        for i, plan in enumerate(result):
            plan.setdefault("chapter_number", start + i)
        return result
