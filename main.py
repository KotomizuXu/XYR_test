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

import readline
readline.parse_and_bind("set editing-mode emacs")
readline.parse_and_bind("bind ^? ed-delete-prev-char")

if sys.version_info < (3, 10):
    print("错误：需要 Python 3.10 或更高版本。")
    print(f"  当前版本：Python {sys.version_info.major}.{sys.version_info.minor}")
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).parent))

from core.pipeline import NovelPipeline, load_config
from core.state_manager import StateManager
from core.llm_client import LLMClient

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

_SYSTEM_PROMPT = """你是一位温和、富有洞察力的文学顾问。你的任务是帮助作者深化他们的故事构思。
请用中文回复。语气温暖、耐心，像一位理解创作者内心世界的朋友。
不要替作者做决定，而是通过细腻的提问和精准的映照，帮助他们发现自己真正想表达的东西。"""


def _read_multiline_feedback() -> str:
    """读取多行调整意见，空行结束。"""
    print("  请告诉我你想调整什么（输入空行结束）：")
    lines = []
    while True:
        try:
            line = input()
        except (KeyboardInterrupt, EOFError):
            print()
            break
        if not line.strip() and lines:
            break
        lines.append(line)
    feedback = "\n".join(lines).strip()
    return feedback if feedback else "yes"


def _confirm(label: str) -> str:
    """展示选项并等待用户确认。返回 'yes' / 'rewrite' / 用户自定义修改意见。"""
    print(f"\n  这是否符合你内心的故事？")
    print(f"  1. 是（确认并继续）")
    print(f"  2. 调整（告诉我哪里需要改，支持多行）")
    print(f"  3. 重写（换一种方向重新生成）")
    try:
        ans = input("  > ").strip()
    except (KeyboardInterrupt, EOFError):
        print()
        return "yes"
    if ans in ("1", ""):
        return "yes"
    if ans == "3":
        return "rewrite"
    if ans == "2":
        return _read_multiline_feedback()
    # 用户直接输入了修改意见（单行快捷方式）
    return ans


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
        "north_star": "请根据作者的故事灵感，用1-2句话提炼这个故事的「北极星」——它最核心的情感真相。这是整个创作的指南针。只输出北极星内容，不要多余解释。",
        "core_concept": "请将作者的故事灵感扩展为2-4句的核心概念描述。更具体地展现故事的核心冲突和情感张力，但不要加入太多细节——留给后续创作空间。只输出核心概念内容。",
        "theme": "请识别这个故事想要探索的深层主题。输出：\n1. 一句话主题陈述\n2. 3个这个故事在追问的关键问题\n只输出主题内容，不要多余解释。",
        "structure": "请根据故事类型推荐一个叙事结构（如三幕结构、英雄之旅、文学弧线等），并简述它如何适用于这个故事。只输出结构建议，不要多余解释。",
    }

    while True:
        print(f"\n{'─'*50}")
        print(f"  正在生成「{section_label}」...")
        result = llm.chat(
            _SYSTEM_PROMPT,
            f"## 上下文\n{context}\n\n## 任务\n{prompts[section_key]}",
            temperature=0.7,
        ).strip()

        print(f"\n  【{section_label}】")
        for line in result.split("\n"):
            print(f"  {line}")

        # 确认循环：确认/调整/重写，调整后继续循环直到确认
        while True:
            action = _confirm(section_label)

            if action == "yes":
                return result
            if action == "rewrite":
                print("  好的，重新生成...")
                break  # 跳出内层循环，外层重新生成

            # 用户输入了调整意见 → 修改 → 再展示 → 继续内层循环
            print(f"  收到，根据你的意见调整：{action}")
            result = llm.chat(
                _SYSTEM_PROMPT,
                f"## 上下文\n{context}\n\n## 之前生成的{section_label}\n{result}\n\n## 用户的调整意见\n{action}\n\n请根据用户意见修改{section_label}，只输出修改后的内容。",
                temperature=0.7,
            ).strip()

            print(f"\n  【{section_label}（修改后）】")
            for line in result.split("\n"):
                print(f"  {line}")


def _braindump(idea: str, name: str, style: str | None) -> str:
    """交互式立项问答。返回丰富后的故事灵感文本。"""
    print(f"\n{'='*50}")
    print("  立项问答 — 让我们一起找到你故事的核心")
    print(f"{'='*50}")
    print(f"\n  原始灵感：{idea}")
    print(f"  小说名称：{name}")
    if style:
        print(f"  风格偏好：{style}")

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
    for section_key, section_label, _ in _BRAINDUMP_SECTIONS:
        if section_key in approved:
            parts.append(f"【{section_label}】\n{approved[section_key]}")

    print(f"\n{'='*50}")
    print("  立项问答完成！以下是你确认的故事核心：")
    print(f"{'='*50}")
    for part in parts:
        print(f"\n{part}")

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# CLI 命令
# ---------------------------------------------------------------------------


def cmd_new():
    print("请输入故事灵感（输入空行结束）：")
    idea_lines = []
    while True:
        try:
            line = input()
        except (KeyboardInterrupt, EOFError):
            print()
            break
        if not line.strip() and idea_lines:
            break
        idea_lines.append(line)
    idea = "\n".join(idea_lines).strip()
    if not idea:
        print("故事灵感不能为空")
        return
    name = input("请输入小说名称：").strip()
    if not name:
        print("小说名称不能为空")
        return
    style = input("请输入小说风格（如：网文爽文、传统文学、悬疑推理，留空使用默认风格）：").strip() or None

    try:
        enriched_idea = _braindump(idea, name, style)
    except KeyboardInterrupt:
        print("\n已取消立项问答")
        return
    except Exception as e:
        print(f"\n立项问答出错：{e}")
        print("你可以重试（python3 main.py new）")
        return

    pipeline = NovelPipeline()
    pipeline.start_new_novel(enriched_idea, name, style=style)


def cmd_continue():
    mgr = StateManager()
    novels = mgr.list_novels()
    if not novels:
        print("暂无进行中的小说")
        return
    print("进行中的小说：")
    for n in novels:
        state = mgr.load(n)
        if state:
            print(f"  - {n} ({state.phase}, {state.current_chapter}/{state.total_chapters}章)")
    name = input("\n请输入要继续的小说名称：").strip()
    if not name:
        return

    pipeline = NovelPipeline()
    pipeline.resume_novel(name)


def cmd_status():
    mgr = StateManager()
    novels = mgr.list_novels()
    if not novels:
        print("暂无小说项目")
        return

    print(f"\n{'='*50}")
    print("小说项目列表")
    print(f"{'='*50}")
    for name in novels:
        state = mgr.load(name)
        if state:
            phase_names = {
                "styling": "风格分析",
                "collecting_params": "参数确认",
                "directing": "构建世界观",
                "plotting": "规划剧情",
                "writing": "撰写中",
                "editing": "编辑润色",
                "complete": "已完成",
            }
            phase_str = phase_names.get(state.phase, state.phase)
            print(f"\n《{name}》")
            print(f"  阶段：{phase_str}")
            print(f"  进度：{min(state.current_chapter, state.total_chapters)}/{state.total_chapters}章")
            idea_preview = state.story_idea[:50]
            print(f"  灵感：{idea_preview}{'...' if len(state.story_idea) > 50 else ''}")
    print()


def cmd_revise():
    mgr = StateManager()
    novels = mgr.list_novels()
    if not novels:
        print("暂无小说项目")
        return
    print("已有小说：")
    for n in novels:
        state = mgr.load(n)
        if state:
            print(f"  - {n} ({state.phase})")
    name = input("\n请输入小说名称：").strip()
    if not name:
        return

    state = mgr.load(name)
    if not state:
        print(f"未找到小说《{name}》")
        return

    print(f"\n《{name}》已完成章节：\n")
    has_chapters = False
    for ch in state.chapters:
        path = Path(ch.edited_path) if ch.edited_path else (Path(ch.draft_path) if ch.draft_path else None)
        if path and path.exists():
            text = path.read_text(encoding="utf-8")
            print(f"  第{ch.chapter_number}章：「{ch.title}」({len(text)}字)")
            has_chapters = True
    if not has_chapters:
        print("  暂无已完成章节")
        return
    chapter_str = input("\n请输入要修订的章节编号：").strip()
    if not chapter_str or not chapter_str.isdigit():
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
