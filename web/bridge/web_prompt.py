"""Web 环境下的 prompt_* 实现。

每个函数通过 WebSocket 向前端发送输入请求，阻塞等待响应。
通过 threading.local() 绑定当前线程的 BridgeSession，支持多会话并发。
"""

import queue
import threading
import uuid

_local = threading.local()


def set_current_session(session):
    _local.session = session


def get_current_session():
    return getattr(_local, "session", None)


class WebUserAbort(Exception):
    pass


def _send_input_request(kind: str, data: dict, timeout: float = 3600):
    session = get_current_session()
    if session is None:
        raise RuntimeError("No active bridge session")

    if session.cancelled.is_set():
        raise WebUserAbort()

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
                raise WebUserAbort()
            continue
        if response.get("request_id") == request_id:
            return response.get("value")
        session.input_queue.put(response)
        break

    raise WebUserAbort()


def web_prompt_choice(message, options, allow_custom=False, default_key=None):
    formatted = [{"key": k, "label": l} for k, l in options]
    return _send_input_request("choice", {
        "message": message,
        "options": formatted,
        "allow_custom": allow_custom,
        "default_key": default_key,
    })


def web_prompt_yes_no(message, default=True):
    result = _send_input_request("yes_no", {
        "message": message,
        "default": default,
    })
    return result in ("true", "yes", True, "True")


def web_prompt_single(message, default="", validator=None):
    result = _send_input_request("single", {
        "message": message,
        "default": default or "",
    })
    return result.strip() if result else ""


def web_prompt_multiline(message, hint=""):
    result = _send_input_request("multiline", {
        "message": message,
        "hint": hint or "",
    })
    return result.strip() if result else ""


def web_prompt_int(message, default, min_val=None, max_val=None):
    result = _send_input_request("int", {
        "message": message.lstrip(),
        "default": default,
        "min_val": min_val,
        "max_val": max_val,
    })
    return int(result)


def web_is_interactive():
    return True
