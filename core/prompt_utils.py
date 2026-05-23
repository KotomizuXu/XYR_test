"""Web 环境下的交互输入封装层。

每个函数通过 WebSocket 向前端发送输入请求，阻塞等待响应。
通过 threading.local() 绑定当前线程的 BridgeSession，支持多会话并发。
"""

from __future__ import annotations

import queue
import threading
import uuid


class UserAbort(Exception):
    """用户主动中断（前端取消 / WebSocket 断开）。"""


# ---------------------------------------------------------------------------
# 会话管理
# ---------------------------------------------------------------------------

_local = threading.local()


def set_current_session(session):
    _local.session = session


def get_current_session():
    return getattr(_local, "session", None)


# ---------------------------------------------------------------------------
# 内部：发送输入请求并等待响应
# ---------------------------------------------------------------------------

def _send_input_request(kind: str, data: dict, timeout: float = 3600):
    session = get_current_session()
    if session is None:
        raise RuntimeError("No active bridge session")

    if session.cancelled.is_set():
        raise UserAbort()

    request_id = str(uuid.uuid4())
    msg = {
        "type": "input_request",
        "request_id": request_id,
        "data": {"kind": kind, **data},
    }
    session.output_queue.put(msg)

    while True:
        try:
            response = session.input_queue.get(timeout=1.0)
        except queue.Empty:
            if session.cancelled.is_set():
                raise UserAbort()
            continue
        if response.get("request_id") == request_id:
            return response.get("value")
        session.input_queue.put(response)
        continue


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------

def prompt_single(message: str, default: str = "",
                  validator=None) -> str:
    """单行输入。通过 WebSocket 向前端请求。"""
    result = _send_input_request("single", {
        "message": message,
        "default": default or "",
    })
    result = result.strip() if result else ""
    if validator is None:
        return result
    ok, msg = validator(result)
    if ok:
        return msg if msg else result
    # 校验失败时通过 output_queue 发送提示，再请求一次
    from core import ui
    ui.warn(msg)
    return prompt_single(message, default=default, validator=validator)


def prompt_multiline(message: str, hint: str = "") -> str:
    """多行输入。通过 WebSocket 向前端请求。"""
    result = _send_input_request("multiline", {
        "message": message,
        "hint": hint or "",
    })
    return result.strip() if result else ""


def prompt_choice(message: str, options: list[tuple[str, str]],
                  allow_custom: bool = False, default_key: str | None = None) -> str:
    """单选菜单。通过 WebSocket 向前端请求。"""
    formatted = [{"key": k, "label": l} for k, l in options]
    return _send_input_request("choice", {
        "message": message,
        "options": formatted,
        "allow_custom": allow_custom,
        "default_key": default_key,
    })


def prompt_yes_no(message: str, default: bool = True) -> bool:
    """y/n 询问。通过 WebSocket 向前端请求。"""
    result = _send_input_request("yes_no", {
        "message": message,
        "default": default,
    })
    return result in ("true", "yes", True, "True")


def prompt_int(message: str, default: int,
               min_val: int | None = None, max_val: int | None = None) -> int:
    """整数输入。通过 WebSocket 向前端请求。"""
    result = _send_input_request("int", {
        "message": message.lstrip(),
        "default": default,
        "min_val": min_val,
        "max_val": max_val,
    })
    return int(result)


def is_interactive() -> bool:
    return True
