"""Plot agent: chapter breakdown and plot points."""

import json
import logging

from core import ui

from agents.base import BaseAgent

logger = logging.getLogger(__name__)

BATCH_SIZE = 5
MAX_SUMMARY_FULL = 30   # 最近 N 条完整摘要
MAX_SUMMARY_SHORT = 50  # 更早的最多保留 N 条简略


class PlotAgent(BaseAgent):
    PROMPT_TEMPLATE = "plotter_system.txt"

    def run(self, outline: dict, world: dict, num_chapters: int, style_guide: dict | None = None, volumes: list | None = None) -> list[dict]:
        system = self.apply_style(self.system_prompt, style_guide)
        world_str = json.dumps(world, ensure_ascii=False, indent=2)
        outline_str = json.dumps(outline, ensure_ascii=False, indent=2)

        if num_chapters <= BATCH_SIZE and not volumes:
            return self._generate_batch(system, world_str, outline_str, 1, num_chapters, num_chapters)

        all_plans: list[dict] = []

        if volumes:
            for vol in volumes:
                vol_size = vol.end_chapter - vol.start_chapter + 1
                vol_batches = (vol_size + BATCH_SIZE - 1) // BATCH_SIZE
                for batch_idx in range(vol_batches):
                    start = vol.start_chapter + batch_idx * BATCH_SIZE
                    end = min(start + BATCH_SIZE - 1, vol.end_chapter)
                    ui.info(f"[编剧] 生成第 {start}-{end} 章计划（卷{vol.number}「{vol.title}」）...")
                    existing_summaries = self._build_existing_summaries(all_plans)
                    batch = self._generate_batch(
                        system, world_str, outline_str, start, end, num_chapters,
                        existing_summaries=existing_summaries,
                        volume_context=f"本批次属于卷{vol.number}「{vol.title}」（第{vol.start_chapter}-{vol.end_chapter}章）。本批次第{end}章是本卷最后一章，请给出有分量的卷末收束。" if end == vol.end_chapter else f"本批次属于卷{vol.number}「{vol.title}」（第{vol.start_chapter}-{vol.end_chapter}章）。",
                    )
                    all_plans.extend(batch)
        else:
            for start in range(1, num_chapters + 1, BATCH_SIZE):
                end = min(start + BATCH_SIZE - 1, num_chapters)
                batch_num = (start - 1) // BATCH_SIZE + 1
                total_batches = (num_chapters + BATCH_SIZE - 1) // BATCH_SIZE
                ui.info(f"[编剧] 生成第 {start}-{end} 章计划（{batch_num}/{total_batches}）...")
                existing_summaries = self._build_existing_summaries(all_plans)
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
        volume_context: str = "",
    ) -> list[dict]:
        user_msg = (
            f"## 世界观设定\n{world_str}\n\n"
            f"## 故事大纲\n{outline_str}\n"
            f"{existing_summaries}\n\n"
            f"## 要求\n"
            f"请仅为第 {start} 到第 {end} 章（共 {total} 章）生成章节计划。"
        )
        if volume_context:
            user_msg += f"\n\n{volume_context}"
        logger.info(f"Plotter: generating chapters {start}-{end} of {total}...")
        result = self.llm.chat_json(
            system, user_msg, temperature=self._temperature()
        )
        if isinstance(result, dict):
            result = result.get("chapters", [])
        if not isinstance(result, list):
            raise ValueError(f"Plotter returned unexpected format: {type(result)}")
        for i, plan in enumerate(result):
            plan.setdefault("chapter_number", start + i)
        return result

    @staticmethod
    def _build_existing_summaries(all_plans: list[dict]) -> str:
        if not all_plans:
            return ""
        total = len(all_plans)
        lines: list[str] = []

        if total <= MAX_SUMMARY_FULL:
            # 全量展示
            for p in all_plans:
                lines.append(f"第{p['chapter_number']}章「{p.get('title', '')}」：{p.get('summary', '')}")
        else:
            # 较早的章节：简略（只保留章号+标题）
            older_count = total - MAX_SUMMARY_FULL
            shown_older = min(older_count, MAX_SUMMARY_SHORT)
            skipped = older_count - shown_older
            if skipped > 0:
                lines.append(f"（前 {skipped} 章已省略，共 {total} 章已规划）")
            for p in all_plans[older_count - shown_older : older_count]:
                lines.append(f"第{p['chapter_number']}章「{p.get('title', '')}」")
            lines.append("─── 以下是近期完整摘要 ───")
            for p in all_plans[total - MAX_SUMMARY_FULL:]:
                lines.append(f"第{p['chapter_number']}章「{p.get('title', '')}」：{p.get('summary', '')}")

        return (
            "\n\n## 已规划的章节摘要（请保持连贯）\n"
            + "\n".join(f"- {l}" for l in lines)
        )
