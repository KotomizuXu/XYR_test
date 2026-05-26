"""Plot agent: chapter breakdown and plot points."""

import json
import logging
import time

import anthropic

from core import ui

from agents.base import BaseAgent

logger = logging.getLogger(__name__)

BATCH_SIZE = 5
MAX_SUMMARY_FULL = 30   # 最近 N 条完整摘要
MAX_SUMMARY_SHORT = 50  # 更早的最多保留 N 条
BATCH_MAX_RETRIES = 3   # 单批次最大重试次数


class PlotAgent(BaseAgent):
    PROMPT_TEMPLATE = "plotter_system.txt"

    def run(
        self,
        outline: dict,
        world: dict,
        num_chapters: int,
        style_guide: dict | None = None,
        volumes: list | None = None,
        existing_plans: list[dict] | None = None,
        on_batch_complete: callable = None,
    ) -> list[dict]:
        system = self.apply_style(self.system_prompt, style_guide)
        world_str = json.dumps(world, ensure_ascii=False, indent=2)
        outline_str = json.dumps(outline, ensure_ascii=False, indent=2)

        if num_chapters <= BATCH_SIZE and not volumes:
            if existing_plans and len(existing_plans) >= num_chapters:
                ui.hint(f"[编剧-恢复] 已有 {len(existing_plans)} 章计划，跳过生成")
                return existing_plans
            return self._generate_batch(system, world_str, outline_str, 1, num_chapters, num_chapters)

        all_plans: list[dict] = list(existing_plans) if existing_plans else []
        completed = len(all_plans)
        if completed > 0:
            ui.hint(f"[编剧-恢复] 已有 {completed} 章计划，从第 {completed + 1} 章继续")

        if volumes:
            for vol in volumes:
                vol_size = vol.end_chapter - vol.start_chapter + 1
                vol_batches = (vol_size + BATCH_SIZE - 1) // BATCH_SIZE
                for batch_idx in range(vol_batches):
                    start = vol.start_chapter + batch_idx * BATCH_SIZE
                    end = min(start + BATCH_SIZE - 1, vol.end_chapter)

                    if end <= completed:
                        continue

                    # 部分完成的批次：裁掉属于当前批次范围的旧数据后重新生成
                    if start <= completed < end:
                        all_plans = [p for p in all_plans if p.get("chapter_number", 0) < start]

                    ui.info(f"[编剧] 生成第 {start}-{end} 章计划（卷{vol.number}「{vol.title}」）...")
                    existing_summaries = self._build_existing_summaries(all_plans)
                    batch = self._generate_batch(
                        system, world_str, outline_str, start, end, num_chapters,
                        existing_summaries=existing_summaries,
                        volume_context=f"本批次属于卷{vol.number}「{vol.title}」（第{vol.start_chapter}-{vol.end_chapter}章）。本批次第{end}章是本卷最后一章，请给出有分量的卷末收束。" if end == vol.end_chapter else f"本批次属于卷{vol.number}「{vol.title}」（第{vol.start_chapter}-{vol.end_chapter}章）。",
                    )
                    all_plans.extend(batch)
                    if on_batch_complete:
                        on_batch_complete(all_plans)
        else:
            start = completed + 1
            while start <= num_chapters:
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
                if on_batch_complete:
                    on_batch_complete(all_plans)
                start += BATCH_SIZE

        logger.info(f"Plotter: done. {len(all_plans)} chapters planned.")
        return all_plans

    def _generate_batch(
        self, system: str, world_str: str, outline_str: str,
        start: int, end: int, total: int,
        existing_summaries: str = "",
        volume_context: str = "",
    ) -> list[dict]:
        user_msg = self._build_batch_prompt(world_str, outline_str, start, end, total, existing_summaries, volume_context)
        logger.info(f"Plotter: generating chapters {start}-{end} of {total}...")

        for attempt in range(BATCH_MAX_RETRIES):
            try:
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
            except anthropic.APIStatusError as e:
                if attempt < BATCH_MAX_RETRIES - 1:
                    wait = 2 ** (attempt + 1)
                    logger.warning(
                        f"Plotter batch {start}-{end} API error {e.status_code} "
                        f"(attempt {attempt+1}/{BATCH_MAX_RETRIES}), retrying in {wait}s"
                    )
                    if e.status_code == 400:
                        user_msg = self._trim_batch_prompt(user_msg, attempt)
                    time.sleep(wait)
                else:
                    raise
            except (anthropic.APIConnectionError, anthropic.RateLimitError) as e:
                if attempt < BATCH_MAX_RETRIES - 1:
                    wait = 2 ** (attempt + 1)
                    logger.warning(
                        f"Plotter batch {start}-{end} connection error "
                        f"(attempt {attempt+1}/{BATCH_MAX_RETRIES}), retrying in {wait}s: {e}"
                    )
                    time.sleep(wait)
                else:
                    raise

    @staticmethod
    def _build_batch_prompt(
        world_str: str, outline_str: str,
        start: int, end: int, total: int,
        existing_summaries: str = "",
        volume_context: str = "",
    ) -> str:
        user_msg = (
            f"## 世界观设定\n{world_str}\n\n"
            f"## 故事大纲\n{outline_str}\n"
            f"{existing_summaries}\n\n"
            f"## 要求\n"
            f"请仅为第 {start} 到第 {end} 章（共 {total} 章）生成章节计划。"
        )
        if volume_context:
            user_msg += f"\n\n{volume_context}"
        return user_msg

    @staticmethod
    def _trim_batch_prompt(user_msg: str, attempt: int) -> str:
        """400 重试时逐步裁剪上下文：先裁已规划摘要，再裁世界观。"""
        if attempt == 0:
            # 第一轮重试：移除已规划章节摘要
            marker = "\n\n## 已规划的章节摘要"
            idx = user_msg.find(marker)
            if idx != -1:
                logger.info("Plotter: trimming existing summaries for 400 retry")
                return user_msg[:idx] + user_msg[user_msg.find("\n\n## 要求"):]
        if attempt >= 1:
            # 第二轮重试：精简世界观到前 500 字
            marker = "## 世界观设定\n"
            idx = user_msg.find(marker)
            if idx != -1:
                after_marker = idx + len(marker)
                end_idx = user_msg.find("\n\n", after_marker)
                if end_idx != -1 and end_idx - after_marker > 500:
                    logger.info("Plotter: truncating world_data for 400 retry")
                    return user_msg[:after_marker] + user_msg[after_marker:after_marker + 500] + "\n...(已精简)" + user_msg[end_idx:]
        return user_msg

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
