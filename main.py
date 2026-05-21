"""Novel Agent CLI - AI多角色协作小说写作助手

Usage:
  python3 main.py new          # 交互式创建新小说
  python3 main.py continue     # 交互式选择并继续创作
  python3 main.py revise       # 交互式选择并修订章节
  python3 main.py status       # 查看所有小说进度
"""

import argparse
import logging
import sys
from pathlib import Path

if sys.version_info < (3, 10):
    print("错误：需要 Python 3.10 或更高版本。")
    print(f"  当前版本：Python {sys.version_info.major}.{sys.version_info.minor}")
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).parent))

from core.pipeline import NovelPipeline, load_config
from core.state_manager import StateManager
from core.llm_client import LLMClient
from core.name_generator import suggest_novel_names
from core.prompt_utils import (
    prompt_single, prompt_multiline, prompt_choice, prompt_yes_no,
    UserAbort, is_interactive,
)
from core import ui
from core.ui import console

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)


# ---------------------------------------------------------------------------
# Braindump: 交互式立项问答（融合 Novel Architect 逐项确认机制）
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
    print(f"\n  这是否符合你内心的故事？")
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
    # adjust：进入多行输入
    try:
        feedback = prompt_multiline("  请告诉我你想调整什么：")
    except UserAbort:
        print("\n  已取消调整，保留当前内容")
        return "yes"
    return feedback if feedback else "yes"


def _braindump_section(llm: LLMClient, section_key: str, section_label: str,
                       idea: str, name: str, style: str | None,
                       approved: dict) -> str | None:
    """逐项生成并确认一个 Braindump 章节。返回确认后的文本，或 None 表示用户退出。"""
    # 构建上下文
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

        # 确认循环：确认/调整/重写，调整后继续循环直到确认
        while True:
            action = _confirm(section_label)

            if action == "yes":
                return result
            if action == "rewrite":
                ui.info("好的，换一种思路重新生成...")
                prev_result = result  # 记录用于反上下文
                break  # 跳出内层循环，外层重新生成

            # 用户输入了调整意见 → 修改 → 再展示 → 继续内层循环
            ui.info(f"收到，根据你的意见调整：{action[:60]}{'...' if len(action) > 60 else ''}")
            result = llm.chat(
                _build_braindump_system(style),
                f"## 上下文\n{context}\n\n## 之前生成的{section_label}\n{result}\n\n## 用户的调整意见\n{action}\n\n请根据用户意见修改{section_label}，只输出修改后的内容。",
                temperature=0.7,
            ).strip()

            ui.show_braindump_result(section_label, result, modified=True)


def _braindump(idea: str, name: str, style: str | None) -> str:
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

    # 组合为富文本 story_idea
    parts = [f"【原始灵感】{idea}"]
    summary_pairs = []
    for section_key, section_label, _ in _BRAINDUMP_SECTIONS:
        if section_key in approved:
            parts.append(f"【{section_label}】\n{approved[section_key]}")
            summary_pairs.append((section_label, approved[section_key]))

    ui.show_braindump_summary(summary_pairs)

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# CLI 命令
# ---------------------------------------------------------------------------


_INVALID_NAME_CHARS = set('\\/:*?"<>|')
_WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_MAX_NAME_LENGTH = 64


def _sanitize_novel_name(name: str) -> tuple[bool, str]:
    """校验小说名是否可作为文件夹名。返回 (是否合法, 错误信息或合法名称)。"""
    name = name.strip()
    if not name:
        return False, "小说名称不能为空"
    if len(name) > _MAX_NAME_LENGTH:
        return False, f"小说名称过长（>{_MAX_NAME_LENGTH} 字符），请使用更短的名字"
    bad = [c for c in name if c in _INVALID_NAME_CHARS]
    if bad:
        return False, f"小说名称包含非法字符：{''.join(set(bad))}（不允许 \\ / : * ? \" < > |）"
    if name.endswith(".") or name.endswith(" "):
        return False, "小说名称不能以 '.' 或空格结尾（Windows 兼容性）"
    base_name = name.split(".", 1)[0].upper()
    if base_name in _WINDOWS_RESERVED_NAMES:
        return False, f"「{name}」是 Windows 保留名，请换一个名字"
    return True, name


def _pick_novel_name(idea: str, style: str | None) -> str | None:
    """通过交互获取小说名。返回 None 表示用户取消。

    流程：先问是否要 AI 起名 → 是则调用 LLM 推 3 候选，循环展示直到用户选定 / 改自定义 / 重生成；
    否则直接走手输 + validator。
    """
    try:
        use_ai = prompt_yes_no("需要 AI 根据故事火花帮你起名吗？", default=True)
    except UserAbort:
        return None

    if not use_ai:
        try:
            return prompt_single("请输入小说名称：", validator=_sanitize_novel_name)
        except UserAbort:
            return None

    config = load_config()
    llm = LLMClient(config)

    while True:
        with console.status("[cyan]AI 正在为你起名...[/cyan]", spinner="dots"):
            candidates = suggest_novel_names(llm, idea, style=style, n=3)

        ui.show_name_candidates(candidates)

        # 构造选项：N 个候选 + 重新生成 + 自己输入
        options: list[tuple[str, str]] = []
        for i, c in enumerate(candidates, 1):
            options.append((f"cand_{i}", f"使用「{c}」"))
        options.append(("regen", "再生成一组候选"))
        options.append(("custom", "自己输入"))

        try:
            choice = prompt_choice("请选择：", options, default_key="cand_1" if candidates else "custom")
        except UserAbort:
            return None

        if choice == "regen":
            continue
        if choice == "custom":
            try:
                return prompt_single("请输入小说名称：", validator=_sanitize_novel_name)
            except UserAbort:
                return None

        # cand_N → 取对应候选 + 校验
        idx = int(choice.split("_")[1]) - 1
        picked = candidates[idx]
        ok, msg = _sanitize_novel_name(picked)
        if ok:
            return msg if isinstance(msg, str) and msg else picked
        # 候选名校验失败（极少见，如长度刚好超），提示让用户改
        ui.warn(f"AI 推荐的「{picked}」校验失败：{msg}。请手动调整或选其他。")
        try:
            return prompt_single("请输入小说名称：", default=picked, validator=_sanitize_novel_name)
        except UserAbort:
            return None


def cmd_new():
    if not is_interactive():
        ui.error("new 命令需要交互式终端")
        return

    ui.banner("Novel Agent", "AI 多角色协作小说写作框架")

    try:
        # 1. 故事火花（多行，先收，让 AI 起名时有依据）
        idea = prompt_multiline("请输入故事灵感（多行可编辑，Ctrl+D 提交）：")
        if not idea:
            ui.warn("故事灵感不能为空")
            return

        # 2. 小说名称（支持 AI 起名）
        name = _pick_novel_name(idea, style=None)
        if not name:
            ui.warn("已取消创建")
            return

        # 3. 风格（单行，可留空）
        style = prompt_single(
            "请输入小说风格（如：网文爽文、传统文学、悬疑推理，留空使用默认风格）：",
        ) or None
    except UserAbort:
        ui.warn("已取消创建")
        return

    try:
        enriched_idea = _braindump(idea, name, style)
    except UserAbort:
        ui.warn("已取消立项问答")
        return
    except Exception as e:
        ui.error(f"立项问答出错：{e}")
        ui.hint("你可以重试（python main.py new）")
        return

    pipeline = NovelPipeline()
    pipeline.start_new_novel(enriched_idea, name, style=style)


def cmd_continue():
    mgr = StateManager()
    novels = mgr.list_novels()
    if not novels:
        ui.warn("暂无进行中的小说")
        return

    ui.banner("继续创作", "选择要恢复的小说项目")

    # 构建菜单选项
    options = []
    for n in novels:
        state = mgr.load(n)
        if state:
            label = f"{n}  ({state.phase}, {state.current_chapter}/{state.total_chapters}章)"
        else:
            label = n
        options.append((n, label))

    try:
        name = prompt_choice("请选择要继续的小说：", options)
    except UserAbort:
        ui.warn("已取消")
        return
    if not name:
        return

    pipeline = NovelPipeline()
    pipeline.resume_novel(name)


def cmd_status():
    mgr = StateManager()
    novels = mgr.list_novels()
    if not novels:
        ui.warn("暂无小说项目")
        return

    phase_names = {
        "styling": "风格分析",
        "collecting_params": "参数确认",
        "directing": "构建世界观",
        "refining": "精修世界观",
        "plotting": "规划剧情",
        "writing": "撰写中",
        "editing": "编辑润色",
        "complete": "已完成",
    }
    rows = []
    for name in novels:
        state = mgr.load(name)
        if not state:
            continue
        idea_preview = state.story_idea[:40] + ("..." if len(state.story_idea) > 40 else "")
        rows.append({
            "name": name,
            "phase": phase_names.get(state.phase, state.phase),
            "current": min(state.current_chapter, state.total_chapters),
            "total": state.total_chapters,
            "idea_preview": idea_preview,
        })
    ui.show_novel_list(rows)


def cmd_revise():
    mgr = StateManager()
    novels = mgr.list_novels()
    if not novels:
        ui.warn("暂无小说项目")
        return

    ui.banner("修订章节", "选择一本已完成创作的小说")

    options = []
    for n in novels:
        state = mgr.load(n)
        label = f"{n} ({state.phase})" if state else n
        options.append((n, label))

    try:
        name = prompt_choice("请选择要修订的小说：", options)
    except UserAbort:
        ui.warn("已取消")
        return

    state = mgr.load(name)
    if not state:
        ui.error(f"未找到小说《{name}》")
        return

    # 列出已完成章节
    chapter_options = []
    for ch in state.chapters:
        path = Path(ch.edited_path) if ch.edited_path else (Path(ch.draft_path) if ch.draft_path else None)
        if path and path.exists():
            text = path.read_text(encoding="utf-8")
            chapter_options.append((str(ch.chapter_number), f"第{ch.chapter_number}章：「{ch.title}」({len(text)}字)"))

    if not chapter_options:
        ui.warn("暂无已完成章节")
        return

    try:
        chapter_str = prompt_choice(f"《{name}》请选择要修订的章节：", chapter_options)
    except UserAbort:
        ui.warn("已取消")
        return
    if not chapter_str:
        return
    chapter = int(chapter_str)

    pipeline = NovelPipeline()
    pipeline.revise_chapter(name, chapter)


def main():
    parser = argparse.ArgumentParser(
        description="Novel Agent - AI多角色协作小说写作助手",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 main.py new       # 创建新小说
  python3 main.py continue  # 继续创作
  python3 main.py revise    # 修订章节
  python3 main.py status    # 查看进度
        """,
    )
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("new", help="创建新小说")
    sub.add_parser("continue", help="继续创作")
    sub.add_parser("revise", help="修订章节")
    sub.add_parser("status", help="查看进度")

    args = parser.parse_args()

    if args.command == "new":
        cmd_new()
    elif args.command == "continue":
        cmd_continue()
    elif args.command == "revise":
        cmd_revise()
    elif args.command == "status":
        cmd_status()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
