"""跨平台交互输入封装层

基于 prompt_toolkit 统一 Win/Mac/Linux 上的命令行交互体验，
解决标准 input() 在 Windows 缺 readline、跨行光标错乱、退格行为不一致等问题。

设计要点：
1. 所有函数使用同一个 PromptSession，启动时一次性配置 KeyBindings。
2. Ctrl+C 抛出 UserAbort（自定义异常），让上层精准 catch；不依赖 KeyboardInterrupt 顺势透传。
3. Ctrl+D / Esc-Enter 显式绑定为提交（Windows 不发 EOF，跨平台一致）。
4. 单行/多行/单选/yes-no/整数 五种输入类型覆盖项目内所有交互场景。
"""

from __future__ import annotations

import sys
from typing import Callable

from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys


class UserAbort(Exception):
    """用户主动中断（Ctrl+C）。上层应 catch 并给出"已取消"提示，而不是让 KeyboardInterrupt 透传。"""


# ---------------------------------------------------------------------------
# 内部：共享 KeyBindings
# ---------------------------------------------------------------------------

def _multiline_bindings() -> KeyBindings:
    """多行模式下的快捷键：Ctrl+D / Esc-Enter 提交，Ctrl+C 抛 UserAbort。"""
    kb = KeyBindings()

    @kb.add(Keys.ControlD)
    def _(event):
        event.current_buffer.validate_and_handle()

    @kb.add(Keys.Escape, Keys.Enter)
    def _(event):
        event.current_buffer.validate_and_handle()

    @kb.add(Keys.ControlC)
    def _(event):
        event.app.exit(exception=UserAbort())

    return kb


def _single_bindings() -> KeyBindings:
    """单行模式：Enter 提交（默认），Ctrl+C 抛 UserAbort，Ctrl+D 视为提交当前内容。"""
    kb = KeyBindings()

    @kb.add(Keys.ControlD)
    def _(event):
        event.current_buffer.validate_and_handle()

    @kb.add(Keys.ControlC)
    def _(event):
        event.app.exit(exception=UserAbort())

    return kb


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def is_interactive() -> bool:
    """检测当前 stdin 是否为 tty。非交互环境（管道、CI）调用 prompt 函数会失败。"""
    try:
        return sys.stdin.isatty()
    except Exception:
        return False


def prompt_single(message: str, default: str = "",
                  validator: Callable[[str], tuple[bool, str]] | None = None) -> str:
    """单行输入。

    Enter 提交，Ctrl+C → UserAbort，Ctrl+D 视为提交当前内容。
    支持：退格、方向键、Home/End、Alt+Backspace 删词、行内自由编辑。

    Args:
        message: 提示文本
        default: 默认值（用户直接回车时返回）
        validator: 可选回调 (text) -> (ok, msg)；不通过时原地打印 msg 并要求重输。

    Returns:
        用户输入的字符串（已 strip）。

    Raises:
        UserAbort: 用户按 Ctrl+C。
    """
    session: PromptSession = PromptSession(key_bindings=_single_bindings())
    while True:
        try:
            text = session.prompt(message, default=default)
        except UserAbort:
            raise
        except (KeyboardInterrupt, EOFError):
            raise UserAbort()
        text = text.strip()
        if validator is None:
            return text
        ok, msg = validator(text)
        if ok:
            return msg if msg else text
        print(f"  {msg}")


def prompt_multiline(message: str,
                     hint: str = "（输入完成后：Ctrl+D 或 Esc 再 Enter 提交，Ctrl+C 取消）") -> str:
    """多行输入。

    方向键可在多行间自由移动，Ctrl+D / Esc-Enter 提交，Ctrl+C → UserAbort。

    Returns:
        多行文本（已 strip）。

    Raises:
        UserAbort: 用户按 Ctrl+C。
    """
    if hint:
        print(hint)
    session: PromptSession = PromptSession(
        key_bindings=_multiline_bindings(),
        multiline=True,
    )
    try:
        text = session.prompt(message)
    except UserAbort:
        raise
    except (KeyboardInterrupt, EOFError):
        raise UserAbort()
    return text.strip()


def prompt_choice(message: str, options: list[tuple[str, str]],
                  allow_custom: bool = False, default_key: str | None = None) -> str:
    """单选菜单。

    Args:
        message: 提示文本
        options: [(key, label), ...]；展示时按编号 1..N 排列。
        allow_custom: True 时若用户输入的不是编号也不是 key，则原样返回该文本。
        default_key: 用户直接回车时返回的 key（如果在 options 中）。

    Returns:
        选中的 key 字符串；allow_custom=True 时可能是用户原样输入。

    Raises:
        UserAbort: 用户按 Ctrl+C。
    """
    print(message)
    for idx, (key, label) in enumerate(options, 1):
        marker = "*" if key == default_key else " "
        print(f"  {marker}{idx}. {label}")
    if allow_custom:
        print("  （或直接输入自定义内容）")

    valid_keys = {key for key, _ in options}
    while True:
        raw = prompt_single("  > ", default="")
        if not raw:
            if default_key:
                return default_key
            if allow_custom:
                return ""
            print("  请输入编号")
            continue
        if raw.isdigit():
            idx = int(raw)
            if 1 <= idx <= len(options):
                return options[idx - 1][0]
            print(f"  编号超出范围（1-{len(options)}）")
            continue
        if raw in valid_keys:
            return raw
        if allow_custom:
            return raw
        print("  请输入有效编号")


def prompt_yes_no(message: str, default: bool = True) -> bool:
    """y/n 询问。default=True 时回车默认 yes。

    Raises:
        UserAbort: 用户按 Ctrl+C。
    """
    suffix = " [Y/n]: " if default else " [y/N]: "
    while True:
        raw = prompt_single(message + suffix, default="").lower()
        if not raw:
            return default
        if raw in ("y", "yes", "是", "好"):
            return True
        if raw in ("n", "no", "否", "不"):
            return False
        print("  请输入 y 或 n")


def prompt_int(message: str, default: int,
               min_val: int | None = None, max_val: int | None = None) -> int:
    """整数输入。空输入用 default；超界或非法时原地提示重输。

    Raises:
        UserAbort: 用户按 Ctrl+C。
    """
    while True:
        raw = prompt_single(message, default="")
        if not raw:
            return default
        try:
            val = int(raw)
        except ValueError:
            print(f"  请输入有效整数（直接回车使用默认值 {default}）")
            continue
        if min_val is not None and val < min_val:
            print(f"  数值不能小于 {min_val}")
            continue
        if max_val is not None and val > max_val:
            print(f"  数值不能大于 {max_val}")
            continue
        return val
