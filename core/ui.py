"""Rich 渲染层 — 集中所有 CLI 展示逻辑

职责：所有"输出"（Panel / Table / 进度条 / 颜色）都走这里。
不收集输入（输入仍走 core/prompt_utils.py）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# Windows GBK 控制台无法编码 ✓/✗/ℹ 等 Unicode 符号 + 中文，
# 在导入 rich 前先把 stdout/stderr 切到 UTF-8（无法编码时用 replace 兜底，不让程序崩）。
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn, TimeElapsedColumn,
)
from rich.table import Table
from rich.text import Text


console = Console()


# ---------------------------------------------------------------------------
# 横幅 / 阶段标题
# ---------------------------------------------------------------------------

def banner(title: str, subtitle: str = "") -> None:
    """顶部主横幅。用于命令入口（new / continue / 完成）。"""
    body = Text(title, style="bold white", justify="center")
    if subtitle:
        body.append("\n")
        body.append(subtitle, style="dim cyan")
    console.print()
    console.print(Panel(body, border_style="bright_cyan", padding=(1, 2)))
    console.print()


def section(title: str, body: str | None = None, style: str = "cyan") -> None:
    """阶段小标题（如「立项问答 — 第 1 节」）。"""
    text = Text(title, style=f"bold {style}")
    if body:
        text.append("\n")
        text.append(body, style="dim")
    console.print(Panel(text, border_style=style, padding=(0, 1)))


def divider(label: str = "", style: str = "dim") -> None:
    """轻量分割线，主要用于 braindump 节之间。"""
    if label:
        console.rule(label, style=style)
    else:
        console.rule(style=style)


# ---------------------------------------------------------------------------
# Braindump / 立项问答
# ---------------------------------------------------------------------------

def show_braindump_intro(idea: str, name: str, style: str | None) -> None:
    table = Table.grid(padding=(0, 1))
    table.add_column(style="dim cyan", no_wrap=True)
    table.add_column()
    table.add_row("原始灵感", idea[:120] + ("..." if len(idea) > 120 else ""))
    table.add_row("小说名称", name)
    if style:
        table.add_row("风格偏好", style)
    console.print(Panel(
        table,
        title="[bold]立项问答 — 让我们一起找到你故事的核心[/bold]",
        border_style="magenta",
        padding=(1, 2),
    ))


def show_braindump_result(label: str, content: str, modified: bool = False) -> None:
    """展示 LLM 生成的某节结果（北极星 / 核心概念 / 主题 / 结构）。"""
    title = f"【{label}】"
    if modified:
        title += "（修改后）"
    console.print(Panel(
        Text(content, style="white"),
        title=f"[bold cyan]{title}[/bold cyan]",
        border_style="cyan",
        padding=(0, 2),
    ))


def show_braindump_summary(parts: list[tuple[str, str]]) -> None:
    """立项问答完成时的总览。parts=[(label, content), ...]"""
    console.rule("[bold magenta]立项问答完成[/bold magenta]", style="magenta")
    for label, content in parts:
        console.print(f"\n[bold cyan]【{label}】[/bold cyan]")
        console.print(content)
    console.print()


# ---------------------------------------------------------------------------
# 精修阶段（refining）—— 展示结构化 dict/list 内容
# ---------------------------------------------------------------------------

def show_refine_block(label: str, content, modified: bool = False) -> None:
    """展示精修阶段的 block 内容（dict/list 经 JSON 美化，str 原样）。"""
    if isinstance(content, (dict, list)):
        body = json.dumps(content, ensure_ascii=False, indent=2)
    else:
        body = str(content)
    title = f"【{label}】" + ("（修改后）" if modified else "")
    console.print(Panel(
        Text(body, style="white"),
        title=f"[bold cyan]{title}[/bold cyan]",
        border_style="cyan",
        padding=(0, 2),
    ))


# ---------------------------------------------------------------------------
# AI 起名候选展示
# ---------------------------------------------------------------------------

def show_name_candidates(candidates: list[str]) -> None:
    if not candidates:
        console.print("[yellow]  AI 未能生成有效候选名，请手动输入[/yellow]")
        return
    table = Table(
        title="[bold cyan]AI 推荐的小说名候选[/bold cyan]",
        border_style="cyan", show_header=True, header_style="bold",
    )
    table.add_column("#", justify="right", style="dim", width=3)
    table.add_column("候选名", style="white bold")
    for i, name in enumerate(candidates, 1):
        table.add_row(str(i), name)
    console.print(table)


# ---------------------------------------------------------------------------
# 参数确认
# ---------------------------------------------------------------------------

def show_param_suggestions(style_name: str, rec_chapters: int,
                            rec_min: int, rec_max: int,
                            chapters_reason: str = "", words_reason: str = "",
                            pace_desc: str = "", reward_desc: str = "") -> None:
    table = Table(
        title=f"[bold]「{style_name}」风格 — 写作参数建议[/bold]",
        border_style="green", show_header=True, header_style="bold green",
    )
    table.add_column("项目", style="dim", no_wrap=True)
    table.add_column("建议值", style="bold white")
    table.add_column("理由", style="dim")

    table.add_row("总章数", f"{rec_chapters} 章", chapters_reason or "—")
    table.add_row("每章字数", f"{rec_min} – {rec_max} 字", words_reason or "—")
    if pace_desc:
        table.add_row("节奏", pace_desc, "")
    if reward_desc:
        table.add_row("反馈密度", reward_desc, "")
    console.print(table)


def show_param_confirmed(total_chapters: int, words_min: int, words_max: int,
                          thresholds: dict[str, int] | None = None) -> None:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="dim cyan", no_wrap=True)
    table.add_column(style="bold white")
    table.add_row("总章数", f"{total_chapters} 章")
    table.add_row("每章字数", f"{words_min} – {words_max} 字")
    if thresholds:
        table.add_row(
            "遗忘阈值",
            f"角色 {thresholds.get('character', '?')} / 支线 {thresholds.get('plotline', '?')} / 伏笔 {thresholds.get('foreshadowing', '?')} 章",
        )
    console.print(Panel(
        table, title="[bold green]✓ 已确认参数[/bold green]",
        border_style="green", padding=(1, 2),
    ))


# ---------------------------------------------------------------------------
# 章节进度
# ---------------------------------------------------------------------------

class ChapterProgress:
    """章节级进度条上下文管理器。底层是 rich.progress.Progress。

    用法：
        with ChapterProgress(total=20, current=3, label="撰写") as prog:
            for i in range(3, 20):
                prog.start_chapter(i+1, "第N章标题")
                prog.update("[作家] 撰写中...")
                ...
                prog.update("[审核] 审稿中...")
                ...
                prog.chapter_done(score=8, consistency=92)
    """

    def __init__(self, total: int, current: int = 0, label: str = "进度"):
        self.total = total
        self.start_count = max(0, current)
        self.label = label
        self._progress: Progress | None = None
        self._task_id = None
        self._current_ch = current

    def __enter__(self):
        self._progress = Progress(
            SpinnerColumn(style="cyan"),
            TextColumn("[bold cyan]{task.description}"),
            BarColumn(bar_width=30, complete_style="green", finished_style="bold green"),
            TaskProgressColumn(),
            TextColumn("·"),
            TimeElapsedColumn(),
            console=console,
            transient=False,
        )
        self._progress.start()
        self._task_id = self._progress.add_task(
            description=f"{self.label}", total=self.total,
            completed=self.start_count,
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._progress:
            self._progress.stop()
        return False

    def start_chapter(self, ch_num: int, title: str) -> None:
        self._current_ch = ch_num
        self._set_desc(f"第{ch_num}章「{title}」")

    def update(self, stage_label: str) -> None:
        self._set_desc(f"第{self._current_ch}章 · {stage_label}")

    def chapter_done(self, info: str = "") -> None:
        if self._progress and self._task_id is not None:
            self._progress.advance(self._task_id, 1)
        if info:
            console.print(f"  [dim green]✓ 第{self._current_ch}章 {info}[/dim green]")

    def _set_desc(self, desc: str) -> None:
        if self._progress and self._task_id is not None:
            self._progress.update(self._task_id, description=desc)


# ---------------------------------------------------------------------------
# 完成 / 状态 / 提示
# ---------------------------------------------------------------------------

def show_completion(novel_name: str, final_dir: Path) -> None:
    body = Text()
    body.append("🎉  ", style="bold yellow")
    body.append(f"《{novel_name}》", style="bold white")
    body.append(" 创作完成！\n\n", style="bold green")
    body.append("输出目录：", style="dim")
    body.append(str(final_dir), style="bold cyan")
    console.print(Panel(
        body, border_style="green", padding=(1, 2),
        title="[bold green]✓ 完成[/bold green]",
    ))


def show_novel_list(rows: list[dict[str, Any]]) -> None:
    """rows: [{name, phase, current, total, idea_preview}, ...]"""
    table = Table(
        title="[bold]小说项目列表[/bold]",
        border_style="cyan", show_header=True, header_style="bold cyan",
    )
    table.add_column("名称", style="bold white")
    table.add_column("阶段", style="magenta")
    table.add_column("进度", style="green", justify="right")
    table.add_column("灵感预览", style="dim")
    for r in rows:
        table.add_row(
            r.get("name", "?"),
            r.get("phase", "?"),
            f"{r.get('current', 0)}/{r.get('total', 0)}",
            r.get("idea_preview", ""),
        )
    console.print(table)


# ---------------------------------------------------------------------------
# 轻量消息（保留 print 语义但带颜色）
# ---------------------------------------------------------------------------

def info(msg: str) -> None:
    console.print(f"[cyan]ℹ[/cyan] {msg}")


def warn(msg: str) -> None:
    console.print(f"[yellow]⚠[/yellow] {msg}")


def success(msg: str) -> None:
    console.print(f"[green]✓[/green] {msg}")


def error(msg: str) -> None:
    console.print(f"[red]✗[/red] {msg}")


def hint(msg: str) -> None:
    """次要提示（恢复跳过 / 自动修正之类）"""
    console.print(f"  [dim]· {msg}[/dim]")
