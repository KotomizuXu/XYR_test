"""Novel Agent CLI - AI多角色协作小说写作助手

Usage:
  py -3.10 main.py new --idea "故事灵感" --name "小说名" [--chapters N]
  py -3.10 main.py continue --name "小说名"
  py -3.10 main.py status
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.pipeline import NovelPipeline
from core.state_manager import StateManager


def cmd_new(args):
    idea = args.idea
    name = args.name
    chapters = args.chapters

    if not idea:
        idea = input("请输入故事灵感：").strip()
    if not name:
        name = input("请输入小说名称：").strip()
    if not idea or not name:
        print("故事灵感和小说名称不能为空")
        return

    pipeline = NovelPipeline()
    pipeline.start_new_novel(idea, name, chapters or None)


def cmd_continue(args):
    name = args.name
    if not name:
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


def cmd_status(_args):
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
                "directing": "构建世界观",
                "plotting": "规划剧情",
                "writing": "撰写中",
                "reviewing": "审核中",
                "editing": "编辑润色",
                "complete": "已完成",
            }
            phase_str = phase_names.get(state.phase, state.phase)
            print(f"\n《{name}》")
            print(f"  阶段：{phase_str}")
            print(f"  进度：{min(state.current_chapter, state.total_chapters)}/{state.total_chapters}章")
            print(f"  灵感：{state.story_idea[:50]}...")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Novel Agent - AI多角色协作小说写作助手",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  py -3.10 main.py new --idea "一个程序员穿越到修仙世界" --name "代码修仙"
  py -3.10 main.py new --idea "末日求生" --name "废土纪元" --chapters 10
  py -3.10 main.py continue --name "代码修仙"
  py -3.10 main.py status
        """,
    )
    sub = parser.add_subparsers(dest="command")

    # new
    p_new = sub.add_parser("new", help="开始创作新小说")
    p_new.add_argument("--idea", "-i", help="故事灵感")
    p_new.add_argument("--name", "-n", help="小说名称")
    p_new.add_argument("--chapters", "-c", type=int, help="章节数量（默认20）")

    # continue
    p_cont = sub.add_parser("continue", help="继续创作")
    p_cont.add_argument("--name", "-n", help="小说名称")

    # status
    sub.add_parser("status", help="查看所有小说进度")

    args = parser.parse_args()

    if args.command == "new":
        cmd_new(args)
    elif args.command == "continue":
        cmd_continue(args)
    elif args.command == "status":
        cmd_status(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
