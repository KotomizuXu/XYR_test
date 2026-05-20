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

from core.pipeline import NovelPipeline
from core.state_manager import StateManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)


def cmd_new():
    idea = input("请输入故事灵感：").strip()
    if not idea:
        print("故事灵感不能为空")
        return
    name = input("请输入小说名称：").strip()
    if not name:
        print("小说名称不能为空")
        return
    style = input("请输入小说风格（如：网文爽文、传统文学、悬疑推理，留空使用默认风格）：").strip() or None

    pipeline = NovelPipeline()
    pipeline.start_new_novel(idea, name, style=style)


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
