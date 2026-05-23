"""Web 输出层 — 所有输出通过 WebSocket 转发给前端。

职责：所有"输出"（banner / section / 进度 / 消息）都通过 session output_queue 发送。
"""

from __future__ import annotations


def _get_session():
    from core.prompt_utils import get_current_session
    return get_current_session()


def _send_output(kind: str, **kwargs):
    session = _get_session()
    if session is None:
        return
    session.output_queue.put({
        "type": "output",
        "data": {"kind": kind, **kwargs},
    })


# ---------------------------------------------------------------------------
# 消息
# ---------------------------------------------------------------------------

def info(msg):
    _send_output("info", message=msg)


def warn(msg):
    _send_output("warn", message=msg)


def success(msg):
    _send_output("success", message=msg)


def error(msg):
    _send_output("error", message=msg)


def hint(msg):
    _send_output("hint", message=msg)


# ---------------------------------------------------------------------------
# 横幅 / 阶段标题
# ---------------------------------------------------------------------------

def banner(title, subtitle=""):
    _send_output("banner", title=title, subtitle=subtitle)


def section(title, body=None, style="cyan"):
    _send_output("section", title=title, body=body, style=style)


def divider(label="", style="dim"):
    _send_output("divider", label=label, style=style)


# ---------------------------------------------------------------------------
# Braindump / 精修 / 参数确认
# ---------------------------------------------------------------------------

def show_braindump_intro(idea, name, style):
    _send_output("braindump_intro", idea=idea, name=name, style=style)


def show_braindump_result(label, content, modified=False):
    _send_output("braindump_result", label=label, content=content, modified=modified)


def show_braindump_summary(parts):
    _send_output("braindump_summary", parts=parts)


def show_refine_block(label, content, modified=False):
    _send_output("refine_block", label=label, content=content, modified=modified)


def show_param_suggestions(style_name, rec_chapters, rec_min, rec_max,
                           chapters_reason="", words_reason="",
                           pace_desc="", reward_desc=""):
    _send_output("param_suggestions",
                 style_name=style_name, rec_chapters=rec_chapters,
                 rec_min=rec_min, rec_max=rec_max,
                 chapters_reason=chapters_reason, words_reason=words_reason,
                 pace_desc=pace_desc, reward_desc=reward_desc)


def show_param_confirmed(total_chapters, words_min, words_max, thresholds=None):
    _send_output("param_confirmed",
                 total_chapters=total_chapters, words_min=words_min,
                 words_max=words_max, thresholds=thresholds)


def show_name_candidates(candidates):
    _send_output("name_candidates", candidates=candidates)


def show_completion(novel_name, final_dir):
    _send_output("completion", novel_name=novel_name, final_dir=str(final_dir))


def show_novel_list(rows):
    _send_output("novel_list", rows=rows)


# ---------------------------------------------------------------------------
# 章节进度
# ---------------------------------------------------------------------------

class ChapterProgress:
    """章节级进度上下文管理器。通过 WebSocket 向前端推送进度事件。"""

    def __init__(self, total, current=0, label="进度"):
        self.total = total
        self.start_count = max(0, current)
        self.label = label
        self._current_ch = current

    def __enter__(self):
        _send_output("progress", action="start", total=self.total,
                     current=self.start_count, label=self.label)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def start_chapter(self, ch_num, title):
        self._current_ch = ch_num
        _send_output("progress", action="update", total=self.total,
                     current=ch_num - 1, label=f"第{ch_num}章「{title}」")

    def update(self, stage_label):
        _send_output("progress", action="update", total=self.total,
                     current=self._current_ch, label=stage_label)

    def chapter_done(self, info=""):
        _send_output("progress", action="chapter_done", total=self.total,
                     current=self._current_ch, info=info)
