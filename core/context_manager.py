"""Long context management via chapter summaries and tracking data."""

import json
import logging

logger = logging.getLogger(__name__)

SUMMARY_PROMPT = """请为以下小说章节生成一份简洁的摘要，包含：
1. 关键事件（2-3句）
2. 角色变化（如有）
3. 重要伏笔或悬念（如有）

摘要字数控制在{max_length}字以内。

章节内容：
{chapter_text}"""

VOLUME_SUMMARY_PROMPT = """请为以下小说一卷的内容生成卷级宏观摘要，用于让后续章节作者了解长程结构。

要求：
1. 提取本卷的主线推进（不超过 3 个核心节点）
2. 关键人物变化与关系演进
3. 已埋设但未回收的伏笔，已收束的伏笔状态
4. 保留原文中标志性的意象、术语和情绪定调（直接引用，不要重述）

字数控制在 {max_length} 字以内。不要重写场景细节，只串联结构。

本卷章节摘要列表：
{chapter_summaries}"""

CONTEXT_TEMPLATE = """## 用户原始需求
{story_idea}

## 世界观与角色参考
{world_ref}

## 故事主线
{outline_ref}

## 前文摘要
{summaries}

## 当前章节剧情要点
{current_plan}"""

FULL_CONTEXT_TEMPLATE = """## 用户原始需求
{story_idea}

## 世界观与角色参考
{world_ref}

## 故事主线
{outline_ref}

## 前文摘要
{summaries}

## 追踪数据
{tracking_context}

## 当前章节剧情要点
{current_plan}"""

# 默认上下文字符预算（运行时会被 config.context_budget.running_context_chars 覆盖）
DEFAULT_MAX_CONTEXT_CHARS = 60000


class ContextManager:
    def __init__(self, llm_client, config: dict):
        self.llm = llm_client
        self.max_summary_length = config["novel"]["summary_max_length"]
        ctx_cfg = config.get("context_budget", {}) or {}
        self.max_context_chars = ctx_cfg.get("running_context_chars", DEFAULT_MAX_CONTEXT_CHARS)
        self.tracking_max_chars = ctx_cfg.get("tracking_context_chars", 8000)
        self.recent_chapters_full = ctx_cfg.get("recent_chapters_full", 3)
        self.recent_chapters_condensed = ctx_cfg.get("recent_chapters_condensed", 7)
        self.volume_summary_max_length = config.get("novel", {}).get("volume_summary_max_length", 1200)
        self.volume_summary_min_chapters = config.get("novel", {}).get("volume_summary_min_chapters", 3)

    def generate_chapter_summary(self, chapter_text: str, chapter_number: int) -> str:
        # 取首尾各3000字，保留章节开头和结尾的关键信息
        if len(chapter_text) > 6000:
            excerpt = chapter_text[:3000] + "\n…（中间省略）…\n" + chapter_text[-3000:]
        else:
            excerpt = chapter_text
        prompt = SUMMARY_PROMPT.format(
            max_length=self.max_summary_length,
            chapter_text=excerpt,
        )
        system = f"你是一个小说编辑助手，擅长提炼故事要点。正在为第{chapter_number}章生成摘要。"
        summary = self.llm.chat(system, prompt, temperature=0.3)
        logger.info(f"Generated summary for chapter {chapter_number}: {summary[:100]}...")
        return summary.strip()

    def generate_volume_summary(self, volume_number: int, volume_title: str,
                                chapter_summaries: list[str], style_guide: dict | None = None) -> str:
        """生成卷级宏观摘要（Level 3）。

        Why: 300 章场景下章节摘要 240K 字，必须再做一层聚合。卷级摘要保留长程结构（伏笔/弧线）
        与原作笔触，给 Writer 远端记忆。
        How to apply: pipeline 在卷末（advance_volume 时）调用一次，结果存入 state。
        """
        if not chapter_summaries:
            return ""
        summaries_text = "\n\n".join(f"第{i}章：{s}" for i, s in enumerate(chapter_summaries, 1))
        prompt = VOLUME_SUMMARY_PROMPT.format(
            max_length=self.volume_summary_max_length,
            chapter_summaries=summaries_text,
        )
        # 沿用风格指南中的 tone，保证卷摘要语言基调与正文一致
        tone = ""
        if style_guide:
            tone = (style_guide.get("tone", {}) or {}).get("overall", "")
        system = (
            f"你是一个小说编辑助手，正在为第{volume_number}卷「{volume_title}」生成卷级宏观摘要。"
            + (f"\n保持基调：{tone}" if tone else "")
        )
        summary = self.llm.chat(system, prompt, temperature=0.3)
        return summary.strip()

    def build_running_context(
        self,
        world_data: dict | None,
        outline: dict | None,
        completed_summaries: list[str],
        current_chapter_plan: dict,
        tracking_context: str = "",
        story_idea: str = "",
        volumes: list | None = None,
        volume_summaries: dict | None = None,
        recent_chapter_excerpts: list[str] | None = None,
        relevant_anchors: str = "",
    ) -> str:
        """构建 Writer 的 running context。

        三级金字塔记忆：
        - Level 1：recent_chapter_excerpts（最近章节原文片段，保近端文风）
        - Level 2：completed_summaries 中按章号配 Tier1/Tier2 滑窗（中程节奏）
        - Level 3：volume_summaries（远端卷级结构）
        - 锚点：relevant_anchors（按本章计划检索的伏笔/角色）
        """
        world_ref = self._condense_world(world_data)
        outline_ref = self._condense_outline(outline)
        current_plan = self._format_chapter_plan(current_chapter_plan)
        idea_text = story_idea.replace("\n", " ")[:1000] if story_idea else "（无）"

        # tracking_context 二次截断（防御性，调用方应已传截断版）
        if tracking_context and len(tracking_context) > self.tracking_max_chars:
            tracking_context = tracking_context[:self.tracking_max_chars] + "\n...(追踪数据已截断)"

        # 组装多层摘要文本
        summaries_text = self._build_layered_summaries(
            completed_summaries,
            volume_summaries or {},
            current_chapter_plan.get("chapter_number", 0),
            volumes,
            recent_chapter_excerpts,
            relevant_anchors,
        )

        volume_info = self._format_volume_info(volumes, current_chapter_plan.get("chapter_number", 0))

        if tracking_context:
            result = FULL_CONTEXT_TEMPLATE.format(
                story_idea=idea_text,
                world_ref=world_ref,
                outline_ref=outline_ref,
                summaries=summaries_text,
                tracking_context=tracking_context,
                current_plan=current_plan,
            )
        else:
            result = CONTEXT_TEMPLATE.format(
                story_idea=idea_text,
                world_ref=world_ref,
                outline_ref=outline_ref,
                summaries=summaries_text,
                current_plan=current_plan,
            )

        if volume_info:
            result = volume_info + "\n\n" + result

        # 总预算兜底截断（不应触发，触发说明上层未做好分配）
        if len(result) > self.max_context_chars:
            logger.warning(f"Context still too long ({len(result)} > {self.max_context_chars}) after layering, hard-truncate")
            result = self._hard_truncate(result, world_ref, outline_ref, tracking_context, current_chapter_plan, story_idea)

        return result

    def _build_layered_summaries(
        self,
        summaries: list[str],
        volume_summaries: dict,
        current_chapter: int,
        volumes: list | None,
        recent_excerpts: list[str] | None,
        relevant_anchors: str,
    ) -> str:
        """组装三级金字塔摘要文本。

        分级策略：
        - Level 3：历史卷的卷级摘要（除当前卷外的所有已完成卷）
        - Level 2 Tier1：最近 recent_chapters_full 章的完整摘要
        - Level 2 Tier2：再向前 recent_chapters_condensed 章的一句话摘要
        - Level 1：最近章节的原文片段（如果传入）
        - 锚点：相关伏笔/角色（query_relevant 输出）
        """
        if not summaries and not volume_summaries and not recent_excerpts:
            return "（这是第一章）"

        sections = []
        total = len(summaries)

        # Level 3：历史卷摘要
        if volume_summaries:
            current_vol_num = self._find_volume_number(volumes, current_chapter)
            l3_lines = []
            for vol_num in sorted(volume_summaries.keys()):
                if current_vol_num and vol_num >= current_vol_num:
                    continue  # 跳过当前及之后的卷
                l3_lines.append(f"### 第{vol_num}卷宏观摘要\n{volume_summaries[vol_num]}")
            if l3_lines:
                sections.append("## 历史卷宏观结构（远端记忆）\n" + "\n\n".join(l3_lines))

        # Level 2 Tier2：condensed 一句话摘要
        full_n = self.recent_chapters_full
        condensed_n = self.recent_chapters_condensed
        tier2 = summaries[max(0, total - full_n - condensed_n): max(0, total - full_n)]
        tier2_start = max(0, total - full_n - condensed_n) + 1
        if tier2:
            t2_lines = []
            dropped = total - len(tier2) - min(full_n, total)
            if dropped > 0:
                t2_lines.append(f"（更早 {dropped} 章已聚合至卷级摘要）")
            for idx, s in enumerate(tier2, tier2_start):
                short = s[:100] + "…" if len(s) > 100 else s
                t2_lines.append(f"第{idx}章（简）：{short}")
            sections.append("## 中程章节梗概\n" + "\n".join(t2_lines))

        # Level 2 Tier1：full 摘要
        tier1 = summaries[-full_n:] if total >= full_n else summaries
        tier1_start = total - len(tier1) + 1
        if tier1:
            t1_lines = [f"第{idx}章摘要：{s}" for idx, s in enumerate(tier1, tier1_start)]
            sections.append("## 最近章节摘要\n" + "\n\n".join(t1_lines))

        # Level 1：原文片段
        if recent_excerpts:
            l1_lines = []
            excerpt_start = current_chapter - len(recent_excerpts)
            for i, ex in enumerate(recent_excerpts):
                ch_num = excerpt_start + i
                l1_lines.append(f"### 第{ch_num}章近端片段\n{ex}")
            sections.append("## 近端原文片段（保持文风延续）\n" + "\n\n".join(l1_lines))

        # 检索锚点
        if relevant_anchors:
            sections.append(relevant_anchors)

        return "\n\n".join(sections) if sections else "（这是第一章）"

    def _find_volume_number(self, volumes: list | None, chapter_number: int) -> int | None:
        if not volumes or not chapter_number:
            return None
        for vol in volumes:
            if vol.start_chapter <= chapter_number <= vol.end_chapter:
                return vol.number
        return None

    def _hard_truncate(self, result: str, world_ref: str, outline_ref: str,
                       tracking_context: str, current_plan: dict, story_idea: str = "") -> str:
        """超预算时硬截断：丢弃 summaries 后半段。"""
        cap = self.max_context_chars
        if len(result) <= cap:
            return result
        # 简单按字符截断尾部，加截断标记
        return result[:cap] + "\n\n...(上下文过长已强制截断，请压缩 summaries)"

    def _format_volume_info(self, volumes: list | None, chapter_number: int) -> str:
        if not volumes or not chapter_number:
            return ""
        for vol in volumes:
            if vol.start_chapter <= chapter_number <= vol.end_chapter:
                pos = chapter_number - vol.start_chapter + 1
                total = vol.end_chapter - vol.start_chapter + 1
                lines = [f"## 当前卷信息\n第{vol.number}卷「{vol.title}」（第{vol.start_chapter}章-第{vol.end_chapter}章）。本章是本卷第{pos}章/共{total}章。"]
                if chapter_number == vol.end_chapter:
                    lines.append("本章是本卷的最后一章，请给出有分量的卷末收束。")
                return "\n".join(lines)
        return ""

    def _condense_world(self, world_data: dict | None) -> str:
        if not world_data:
            return "（暂无）"
        lines = []
        if "name" in world_data:
            lines.append(f"世界观：{world_data['name']}")
        if "tone" in world_data:
            lines.append(f"整体基调：{world_data['tone']}")
        if "setting" in world_data:
            lines.append(f"背景：{world_data['setting']}")
        if "narrative_perspective" in world_data:
            lines.append(f"叙事视角：{world_data['narrative_perspective']}")
        if "unique_elements" in world_data:
            elements = world_data["unique_elements"]
            if isinstance(elements, list) and elements:
                lines.append(f"世界特色：{'；'.join(str(e) for e in elements[:8])}")
        if "rules" in world_data:
            lines.append(f"世界规则：{world_data['rules']}")
        if "social_structure" in world_data:
            ss = world_data["social_structure"]
            if isinstance(ss, dict):
                parts = []
                for k in ("political_system", "economy", "social_classes", "culture"):
                    if ss.get(k):
                        parts.append(str(ss[k]))
                if parts:
                    lines.append(f"社会结构：{'；'.join(parts)}")
        if "geography" in world_data:
            geo = world_data["geography"]
            if isinstance(geo, dict):
                locs = geo.get("main_locations", [])
                if locs:
                    loc_names = [l.get("name", str(l)) if isinstance(l, dict) else str(l) for l in locs[:8]]
                    lines.append(f"主要地点：{'、'.join(loc_names)}")
        if "factions" in world_data:
            factions = world_data["factions"]
            if isinstance(factions, list) and factions:
                names = [f.get("name", str(f)) if isinstance(f, dict) else str(f) for f in factions[:8]]
                lines.append(f"势力：{'、'.join(names)}")
        if "history" in world_data:
            history = world_data["history"]
            if isinstance(history, list) and history:
                events = [h.get("event", str(h)) if isinstance(h, dict) else str(h) for h in history[:5]]
                lines.append(f"重要历史事件：{'；'.join(events)}")
        if "daily_life" in world_data:
            dl = world_data["daily_life"]
            if isinstance(dl, dict):
                parts = [f"{k}：{v}" for k, v in dl.items() if v]
                if parts:
                    lines.append(f"日常生活：{'；'.join(parts[:6])}")
        if "characters" in world_data:
            chars = world_data["characters"]
            if isinstance(chars, list):
                lines.append("角色：")
                for c in chars[:12]:
                    name = c.get("name", "")
                    role = c.get("role", "")
                    desc = c.get("description", c.get("personality", ""))
                    role_prefix = f"（{role}）" if role else ""
                    bg_parts = []
                    bg = c.get("background", {})
                    if isinstance(bg, dict):
                        for bk, bv in bg.items():
                            if bv:
                                bg_parts.append(f"{bk}：{bv}")
                    bg_str = f" [背景：{'；'.join(bg_parts)}]" if bg_parts else ""
                    lines.append(f"  - {name}{role_prefix}：{desc}{bg_str}")
        return "\n".join(lines) if lines else str(world_data)

    def _condense_outline(self, outline: dict | None) -> str:
        if not outline:
            return "（暂无）"
        lines = []
        if "theme" in outline:
            lines.append(f"主题：{outline['theme']}")
        if "three_act" in outline:
            for act_name, act_desc in outline["three_act"].items():
                lines.append(f"{act_name}：{act_desc}")
        if "ending" in outline:
            lines.append(f"结局方向：{outline['ending']}")
        if "key_turning_points" in outline:
            points = outline["key_turning_points"]
            if points:
                lines.append("关键转折点：" + "；".join(str(p) for p in points))
        return "\n".join(lines) if lines else str(outline)

    def _format_summaries(self, summaries: list[str]) -> str:
        if not summaries:
            return "（这是第一章）"
        parts = []
        for i, s in enumerate(summaries, 1):
            parts.append(f"第{i}章摘要：{s}")
        return "\n\n".join(parts)

    def _format_chapter_plan(self, plan: dict) -> str:
        lines = [f"章节标题：{plan.get('title', '未定')}"]
        if "summary" in plan:
            lines.append(f"概要：{plan['summary']}")
        if "plot_points" in plan:
            lines.append("剧情要点：")
            for pp in plan["plot_points"]:
                lines.append(f"  - {pp}")
        if "emotional_arc" in plan:
            lines.append(f"情绪线：{plan['emotional_arc']}")
        if "emotional_type" in plan:
            lines.append(f"情绪类型：{plan['emotional_type']}")
        if "emotional_intensity" in plan:
            lines.append(f"情绪强度：{plan['emotional_intensity']}")
        if "characters_involved" in plan:
            lines.append(f"出场角色：{', '.join(plan['characters_involved'])}")
        if "foreshadowing" in plan:
            lines.append("伏笔：")
            for fs in plan["foreshadowing"]:
                if isinstance(fs, dict):
                    lines.append(f"  - {fs.get('content', fs)}（可见性：{fs.get('visibility', '?')}，计划回收：第{fs.get('planned_reveal', '?')}章）")
                else:
                    lines.append(f"  - {fs}")
        if "active_plotlines" in plan:
            lines.append(f"活跃线索：{', '.join(plan['active_plotlines'])}")
        if "act" in plan:
            lines.append(f"所属幕：{plan['act']}")
        if "cliffhanger" in plan:
            lines.append(f"章节钩子：{plan['cliffhanger']}")
        if "scene_structure" in plan:
            lines.append(f"场景结构：{plan['scene_structure']}")
        if "tension_level" in plan:
            lines.append(f"张力等级：{plan['tension_level']}")
        if "location" in plan:
            lines.append(f"场景地点：{plan['location']}")
        if "time" in plan:
            lines.append(f"故事时间：{plan['time']}")
        if "previous_link" in plan:
            lines.append(f"承上启下：{plan['previous_link']}")
        if "opening_hook_type" in plan:
            lines.append(f"章首引子类型：{plan['opening_hook_type']}")
        if "ending_hook_type" in plan:
            lines.append(f"章尾悬念类型：{plan['ending_hook_type']}")
        if "characters_on_stage" in plan:
            lines.append(f"实际登场角色：{', '.join(plan['characters_on_stage'])}")
        if "scene_list" in plan and plan["scene_list"]:
            lines.append("场景列表：")
            for scene in plan["scene_list"]:
                if isinstance(scene, dict):
                    lines.append(f"  - {scene.get('name', '?')}（地点：{scene.get('location', '?')}，目的：{scene.get('purpose', '?')}）")
                else:
                    lines.append(f"  - {scene}")
        return "\n".join(lines)
