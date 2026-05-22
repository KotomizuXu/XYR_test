"""交互桥接层：在 Web 环境下将 core.prompt_utils 和 core.ui 替换为 WebSocket 版本。

关键：install_web_bridge() 必须在 import core.pipeline 之前调用，
否则 pipeline.py 的 from core.prompt_utils import ... 会拿到 CLI 版引用。
"""

import core.prompt_utils
import core.ui
import core.llm_client

from web.bridge import web_prompt, web_ui

_original_prompt_utils = {}
_original_ui = {}
_original_spinner = None


def install_web_bridge():
    global _original_prompt_utils, _original_ui, _original_spinner

    # 保存原始版本
    _original_prompt_utils = {
        "prompt_choice": core.prompt_utils.prompt_choice,
        "prompt_yes_no": core.prompt_utils.prompt_yes_no,
        "prompt_single": core.prompt_utils.prompt_single,
        "prompt_multiline": core.prompt_utils.prompt_multiline,
        "prompt_int": core.prompt_utils.prompt_int,
        "is_interactive": core.prompt_utils.is_interactive,
        "UserAbort": core.prompt_utils.UserAbort,
    }
    _original_ui = {
        "info": core.ui.info,
        "warn": core.ui.warn,
        "success": core.ui.success,
        "error": core.ui.error,
        "hint": core.ui.hint,
        "banner": core.ui.banner,
        "section": core.ui.section,
        "divider": core.ui.divider,
        "show_refine_block": core.ui.show_refine_block,
        "show_param_suggestions": core.ui.show_param_suggestions,
        "show_param_confirmed": core.ui.show_param_confirmed,
        "show_braindump_intro": core.ui.show_braindump_intro,
        "show_braindump_result": core.ui.show_braindump_result,
        "show_braindump_summary": core.ui.show_braindump_summary,
        "show_name_candidates": core.ui.show_name_candidates,
        "show_completion": core.ui.show_completion,
        "show_novel_list": core.ui.show_novel_list,
        "ChapterProgress": core.ui.ChapterProgress,
    }
    _original_spinner = getattr(core.llm_client, "Spinner", None)

    # 替换 prompt_utils
    core.prompt_utils.prompt_choice = web_prompt.web_prompt_choice
    core.prompt_utils.prompt_yes_no = web_prompt.web_prompt_yes_no
    core.prompt_utils.prompt_single = web_prompt.web_prompt_single
    core.prompt_utils.prompt_multiline = web_prompt.web_prompt_multiline
    core.prompt_utils.prompt_int = web_prompt.web_prompt_int
    core.prompt_utils.is_interactive = web_prompt.web_is_interactive
    core.prompt_utils.UserAbort = web_prompt.WebUserAbort

    # 替换 ui
    core.ui.info = web_ui.info
    core.ui.warn = web_ui.warn
    core.ui.success = web_ui.success
    core.ui.error = web_ui.error
    core.ui.hint = web_ui.hint
    core.ui.banner = web_ui.banner
    core.ui.section = web_ui.section
    core.ui.divider = web_ui.divider
    core.ui.show_refine_block = web_ui.show_refine_block
    core.ui.show_param_suggestions = web_ui.show_param_suggestions
    core.ui.show_param_confirmed = web_ui.show_param_confirmed
    core.ui.show_braindump_intro = web_ui.show_braindump_intro
    core.ui.show_braindump_result = web_ui.show_braindump_result
    core.ui.show_braindump_summary = web_ui.show_braindump_summary
    core.ui.show_name_candidates = web_ui.show_name_candidates
    core.ui.show_completion = web_ui.show_completion
    core.ui.show_novel_list = web_ui.show_novel_list
    core.ui.ChapterProgress = web_ui.WebChapterProgress

    # 替换 LLMClient 的 Spinner（Web 环境下不输出到终端）
    class _NoopSpinner:
        def __init__(self, *a, **kw):
            pass
        def start(self):
            pass
        def stop(self):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass
    core.llm_client.Spinner = _NoopSpinner


def uninstall_web_bridge():
    for name, func in _original_prompt_utils.items():
        setattr(core.prompt_utils, name, func)
    for name, func in _original_ui.items():
        setattr(core.ui, name, func)
    if _original_spinner is not None:
        core.llm_client.Spinner = _original_spinner
