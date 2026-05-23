"""交互式立项问答（Braindump）与负面约束提取。

从原始灵感通过 LLM 逐步生成北极星、核心概念、主题、叙事结构，
每步由用户确认/调整/重写。最后从结果中提取用户明确表达的负面约束。
"""

from __future__ import annotations

from core.llm_client import LLMClient
from core.pipeline import load_config
from core.prompt_utils import UserAbort, prompt_choice, prompt_multiline
from core import ui


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

_BRAINDUMP_SECTIONS = [
    ("north_star", "北极星（核心情感）", "north_star"),
    ("core_concept", "核心概念", "core_concept"),
    ("theme", "主题与关键问题", "theme"),
    ("structure", "叙事结构", "structure"),
]

_BRAINDUMP_SYSTEM_BASE = """你是一位资深的故事顾问，帮助作者深化他们的故事构思。
请用中文回复。"""

_BRAINDUMP_STYLE_GUIDANCE = """

## 目标读者风格
作者期望的小说风格是：{style}

请用与该风格相匹配的语气和措辞回应：
- 网文 / 爽文 / 甜文 / 言情：用通俗、轻快、贴近读者的措辞，关注"爽点 / 情感钩子 / 节奏冲突 / 角色魅力"，避免"情感真相 / 深层主题 / 文学弧线"这类拔高的措辞
- 严肃文学 / 现实主义：可使用文学化措辞，关注主题、隐喻、人物弧光
- 悬疑 / 推理：聚焦悬念布局、信息差、反转节奏
- 玄幻 / 仙侠 / 科幻：聚焦设定独特性、世界观规则、力量体系

整体原则：你的措辞和关注点要匹配作者的风格选择，而不是把所有故事都引向文学化方向。"""

_BRAINDUMP_NEUTRAL_TAIL = """
不要替作者做决定，而是通过提问和映照帮助他们澄清自己想表达的东西。"""

_REWRITE_DIRECTIVE = """

## 重写要求
用户对上一版不满意，请彻底换一种思路、措辞、角度，与上一版表述明显不同；避免在原方向上做表面调整。"""


# ---------------------------------------------------------------------------
# 内部函数
# ---------------------------------------------------------------------------

def _build_braindump_system(style: str | None, is_rewrite: bool = False) -> str:
    parts = [_BRAINDUMP_SYSTEM_BASE]
    if style:
        parts.append(_BRAINDUMP_STYLE_GUIDANCE.format(style=style))
    parts.append(_BRAINDUMP_NEUTRAL_TAIL)
    if is_rewrite:
        parts.append(_REWRITE_DIRECTIVE)
    return "".join(parts)


def _confirm(label: str) -> str:
    """展示选项并等待用户确认。返回 'yes' / 'rewrite' / 用户自定义修改意见。"""
    try:
        choice = prompt_choice(
            "  请选择：",
            [
                ("yes", "是（确认并继续）"),
                ("adjust", "调整（告诉我哪里需要改，支持多行）"),
                ("rewrite", "重写（换一种方向重新生成）"),
            ],
            default_key="yes",
        )
    except UserAbort:
        return "yes"

    if choice == "yes":
        return "yes"
    if choice == "rewrite":
        return "rewrite"
    try:
        feedback = prompt_multiline("  请告诉我你想调整什么：")
    except UserAbort:
        return "yes"
    return feedback if feedback else "yes"


def _braindump_section(llm: LLMClient, section_key: str, section_label: str,
                       idea: str, name: str, style: str | None,
                       approved: dict) -> str | None:
    """逐项生成并确认一个 Braindump 章节。"""
    context_parts = [f"原始灵感：{idea}", f"小说名称：{name}"]
    if style:
        context_parts.append(f"风格偏好：{style}")
    for key, label, _ in _BRAINDUMP_SECTIONS:
        if key in approved:
            context_parts.append(f"已确认的{label}：{approved[key]}")
    context = "\n".join(context_parts)

    prompts = {
        "north_star": "请根据作者的故事灵感，用 1-2 句话提炼这个故事**最核心的东西**——可以是核心情感、核心冲突、核心钩子、核心爽点，取决于故事类型。只输出内容，不要多余解释。",
        "core_concept": "请将作者的故事灵感扩展为 2-4 句的核心概念描述，清晰展现故事的**主线张力**（情感、冲突、悬念或爽感都可以）。不要加入太多细节，留给后续创作空间。只输出内容。",
        "theme": "请描述这个故事想要呈现的**核心要点**：\n1. 一句话故事定位（讲什么 / 想让读者感受什么）\n2. 3 个故事里需要回答 / 解决 / 满足的关键问题或读者期待\n只输出内容，不要多余解释。",
        "structure": "请根据故事类型推荐一个**合适的叙事结构**（三幕结构、英雄之旅、文学弧线、网文升级流、单元剧、双线交织等都可以，取决于故事），并简述它如何适用于这个故事。只输出内容，不要多余解释。",
    }

    prev_result: str | None = None

    while True:
        ui.divider(f"正在生成「{section_label}」", style="dim cyan")
        if prev_result is None:
            user_msg = f"## 上下文\n{context}\n\n## 任务\n{prompts[section_key]}"
            system_msg = _build_braindump_system(style)
            temperature = 0.7
        else:
            user_msg = (
                f"## 上下文\n{context}\n\n"
                f"## 之前生成的{section_label}（用户不满意，请勿沿用此方向）\n{prev_result}\n\n"
                f"## 任务\n{prompts[section_key]}\n\n"
                f"请彻底换一种角度、措辞、节奏重新生成，与上一版表述明显不同。"
            )
            system_msg = _build_braindump_system(style, is_rewrite=True)
            temperature = 0.9

        result = llm.chat(system_msg, user_msg, temperature=temperature).strip()

        ui.show_braindump_result(section_label, result, modified=(prev_result is not None))

        while True:
            action = _confirm(section_label)

            if action == "yes":
                return result
            if action == "rewrite":
                ui.info("好的，换一种思路重新生成...")
                prev_result = result
                break

            ui.info(f"收到，根据你的意见调整：{action[:120]}{'...' if len(action) > 120 else ''}")
            result = llm.chat(
                _build_braindump_system(style),
                f"## 上下文\n{context}\n\n## 之前生成的{section_label}\n{result}\n\n## 用户的调整意见\n{action}\n\n请根据用户意见修改{section_label}，只输出修改后的内容。",
                temperature=0.7,
            ).strip()

            ui.show_braindump_result(section_label, result, modified=True)


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------

def braindump(idea: str, name: str, style: str | None) -> str:
    """交互式立项问答。返回丰富后的故事灵感文本。"""
    ui.show_braindump_intro(idea, name, style)

    config = load_config()
    llm = LLMClient(config)
    approved = {}

    for section_key, section_label, _ in _BRAINDUMP_SECTIONS:
        result = _braindump_section(llm, section_key, section_label, idea, name, style, approved)
        if result is None:
            break
        approved[section_key] = result

    parts = [f"【原始灵感】{idea}"]
    summary_pairs = []
    for section_key, section_label, _ in _BRAINDUMP_SECTIONS:
        if section_key in approved:
            parts.append(f"【{section_label}】\n{approved[section_key]}")
            summary_pairs.append((section_label, approved[section_key]))

    ui.show_braindump_summary(summary_pairs)

    return "\n\n".join(parts)


def extract_negative_constraints(enriched_idea: str, style: str | None) -> str | None:
    """从立项问答结果中提取用户的负面约束（如"不要升级流"），追加到风格描述。"""
    config = load_config()
    llm = LLMClient(config)

    system = "你是一个文本分析助手。只输出结果，不要解释。"
    user_msg = (
        "请从以下故事构思中提取用户明确表达的**负面约束**——即用户说\"不要\"\"避免\"\"禁止\"\"没有\"\"不能\"等"
        "否定表述的内容（如\"不要升级流\"→\"禁止升级/等级体系\"，\"避免后宫\"→\"禁止后宫/多角恋\"）。\n\n"
        f"{enriched_idea}\n\n"
        "如果存在负面约束，请输出一行逗号分隔的简短约束列表（如：禁止升级体系,禁止后宫,避免虐心）。\n"
        "如果没有负面约束，只输出\"无\"。"
    )

    try:
        result = llm.chat(system, user_msg, temperature=0.2).strip()
    except Exception:
        return style

    if not result or result == "无":
        return style

    constraint_text = f"【用户明确禁止的元素：{result}】"
    if style:
        return f"{style} {constraint_text}"
    return constraint_text
