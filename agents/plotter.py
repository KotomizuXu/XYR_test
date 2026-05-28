"""Plot agent: chapter breakdown and plot points."""

import json
import logging
import re
import time

import anthropic

from core import ui

from agents.base import BaseAgent

logger = logging.getLogger(__name__)

BATCH_SIZE = 5
MAX_SUMMARY_FULL = 30   # 最近 N 条完整摘要
MAX_SUMMARY_SHORT = 50  # 更早的最多保留 N 条
BATCH_MAX_RETRIES = 3   # 单批次最大重试次数
EXISTING_SUMMARIES_CHAR_CAP = 20000  # 已规划摘要拼接上限（300 章累计可达 50K+，会挤爆 token）

# 章节标题前缀清洗：剥离 LLM 自加的"第N卷/卷X/第N幕/Volume N"等前缀。
# 注意：故意不清"第N章"——剧情元素可能含"第三章隔间"这类合法 title。
_TITLE_PREFIX_RE = re.compile(
    r"^\s*(?:"
    r"第[一二三四五六七八九十百零\d]+[卷幕部]"            # 第二卷 / 第三幕 / 第一部
    r"|卷[一二三四五六七八九十\d]+"                       # 卷二
    r"|[Vv]ol(?:ume)?[\s\.]*\d+"                           # Vol.2 / Volume 3
    r")[\s·:：、\-—,，]*"
)


class PlotAgent(BaseAgent):
    PROMPT_TEMPLATE = "plotter_system.txt"

    def _validate_chapter_plan_fields(self, plan: dict) -> list[str]:
        """验证章节计划是否包含所有必需字段，返回缺失字段列表。"""
        required_fields = [
            "chapter_number", "title", "summary", "plot_points", "scene_list",
            "characters_on_stage", "emotional_arc", "tension_level",
            "opening_hook_type", "ending_hook_type", "foreshadowing",
            "active_plotlines", "act", "location", "time", "duration",
        ]
        return [f for f in required_fields if f not in plan]

    def regenerate_chapters(
        self,
        chapter_plans: list[dict],
        target_chapters: list[int],
        audit_feedback: str,
        old_plans: list[dict],
        world: dict,
        outline: dict,
        style_guide: dict | None = None,
    ) -> list[dict]:
        """重写指定章节的计划，基于审计反馈修复问题。

        对齐 Writer.rewrite() 的 6 项机制：
        1. 温度提升 +0.25（上限 0.95）
        2. 7 条重写规则写在 user_msg
        3. 跳过（使用独立 prompt 文件）
        4. 上下文截断 plotter_rewrite_ctx_cap = 10000
        5. JSON 字段完整性校验
        6. 每轮保存文件由调用方负责
        """
        # 加载重写专用 system prompt
        rewrite_prompt_path = PROMPTS_DIR / "outline_rewrite_system.txt"
        if rewrite_prompt_path.exists():
            system = rewrite_prompt_path.read_text(encoding="utf-8")
        else:
            system = self.apply_style(self.system_prompt, style_guide)

        # 构建重写上下文
        world_str = json.dumps(world, ensure_ascii=False, indent=2)
        outline_str = json.dumps(outline, ensure_ascii=False, indent=2)

        # 上下文截断（对齐 Writer.rewrite 的 rewrite_ctx_cap）
        ctx_cap = self.config.get("outline_audit", {}).get("plotter_rewrite_ctx_cap", 10000)
        existing_summaries = self._build_existing_summaries(chapter_plans)
        if len(existing_summaries) > ctx_cap:
            existing_summaries = existing_summaries[:ctx_cap] + "\n...(摘要已截断)"

        # 温度提升（对齐 Writer.rewrite 的 +0.25）
        base_temp = self._temperature()
        boost = self.config.get("outline_audit", {}).get("rewrite_temperature_boost", 0.25)
        rewrite_temp = min(base_temp + boost, 0.95)

        # 7 条重写规则（对齐 Writer.rewrite 的规则列表）
        rewrite_rules = (
            "## 重写要求\n"
            "请针对审计反馈中指出的每一个问题进行实质性修改。具体要求：\n"
            "1. 对 major 级别问题：必须大幅重写相关情节点，不能只改几个词或做表面调整\n"
            "2. 对 warning 级别问题：必须有可感知的改善，不能原样保留\n"
            "3. 如果审计指出\"能力超标\"：必须降低角色在该能力域的表现，或增加合理的铺垫解释\n"
            "4. 如果审计指出\"世界规则违反\"：必须修改情节使其符合已建立的世界观规则\n"
            "5. 如果审计指出\"伏笔断裂\"：必须补充 planted/revealed 的对应关系\n"
            "6. 保留质量评分 ≥ 7 的维度，不要为了修复问题而破坏原有的好设计\n"
            "7. 输出完整的章节计划 JSON，不要省略任何字段"
        )

        # 为每个目标章节构建重写请求
        rewritten_plans = []
        for target_ch_num, old_plan in zip(target_chapters, old_plans):
            # 获取邻居章节（前一章和后一章）
            prev_plan = next((p for p in chapter_plans if p.get("chapter_number") == target_ch_num - 1), None)
            next_plan = next((p for p in chapter_plans if p.get("chapter_number") == target_ch_num + 1), None)

            # 构建 user_msg
            user_msg = f"## 世界观设定\n{world_str}\n\n"
            user_msg += f"## 故事大纲\n{outline_str}\n\n"
            user_msg += f"## 前后章节摘要（保持连贯，上限 {ctx_cap} 字符）\n{existing_summaries}\n\n"

            if prev_plan:
                user_msg += f"## 前一章计划（第{target_ch_num - 1}章）\n"
                user_msg += json.dumps(prev_plan, ensure_ascii=False, indent=2) + "\n\n"

            if next_plan:
                user_msg += f"## 后一章计划（第{target_ch_num + 1}章）\n"
                user_msg += json.dumps(next_plan, ensure_ascii=False, indent=2) + "\n\n"

            user_msg += f"## 旧版计划（第{target_ch_num}章，用户不满意，请勿沿用此方向）\n"
            user_msg += json.dumps(old_plan, ensure_ascii=False, indent=2) + "\n\n"

            user_msg += f"## 审计反馈（必须修复以下问题）\n{audit_feedback}\n\n"
            user_msg += rewrite_rules

            # 调用 LLM 重写
            logger.info(f"Plotter: rewriting chapter {target_ch_num} (temp={rewrite_temp:.2f})...")

            for attempt in range(2):  # 最多重试 1 次
                new_plan = self.llm.chat_json(system, user_msg, temperature=rewrite_temp)

                if not isinstance(new_plan, dict):
                    logger.warning(f"Plotter: rewrite returned non-dict for chapter {target_ch_num} (attempt {attempt+1})")
                    continue

                # 输出校验：检查必需字段（对齐 Writer.rewrite 的字数校验）
                missing_fields = self._validate_chapter_plan_fields(new_plan)
                if missing_fields and attempt == 0:
                    logger.warning(
                        f"Plotter: rewritten chapter {target_ch_num} missing fields: {missing_fields}, retrying..."
                    )
                    retry_msg = user_msg + f"\n\n注意：上次输出缺少以下字段：{missing_fields}，请确保输出完整的 JSON。"
                    continue

                # 清洗标题（复用现有逻辑）
                if "title" in new_plan:
                    new_plan["title"] = self._sanitize_title(new_plan["title"])

                # 确保 chapter_number 正确
                new_plan["chapter_number"] = target_ch_num

                rewritten_plans.append(new_plan)
                logger.info(f"Plotter: chapter {target_ch_num} rewritten successfully")
                break
            else:
                # 两次都失败，保留旧版本
                logger.error(f"Plotter: failed to rewrite chapter {target_ch_num}, keeping old version")
                rewritten_plans.append(old_plan)

        return rewritten_plans

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
                    batch_start_idx = len(all_plans)
                    all_plans.extend(batch)
                    if on_batch_complete:
                        on_batch_complete(all_plans, batch_start_idx, batch)
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
                batch_start_idx = len(all_plans)
                all_plans.extend(batch)
                if on_batch_complete:
                    on_batch_complete(all_plans, batch_start_idx, batch)
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
                    if plan.get("title"):
                        plan["title"] = self._sanitize_title(plan["title"])
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
    def _sanitize_title(title: str) -> str:
        """剥离 LLM 自加的'第N卷'/'卷X'/'第N幕'/'Volume N' 等卷幕前缀。

        Why: title 字段只该写本章主题词组；卷/幕归属由 act 字段和 state.volumes 表达。
        LLM 偶发把卷名拼进 title（如'第二卷：虚假生路 - 沉溺'），导致前端 '第N章 {title}'
        渲染时出现重复卷名。
        """
        if not isinstance(title, str):
            return title
        cleaned = _TITLE_PREFIX_RE.sub("", title).strip()
        return cleaned or title

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
        )[:EXISTING_SUMMARIES_CHAR_CAP]
