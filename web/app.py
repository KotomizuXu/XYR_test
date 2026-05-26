"""FastAPI 应用：WebSocket 端点 + REST API + Vue SPA 静态文件。"""

import asyncio
import queue
import signal
import threading

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from web.bridge.session import BridgeSession, session_manager
from core.prompt_utils import set_current_session, UserAbort as WebUserAbort
from core.pipeline import _PhaseHandledError
from web.routers import novels

app = FastAPI(title="Novel Agent Web")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(novels.router, prefix="/api")

# Vue SPA 静态文件（构建后）
from pathlib import Path
_frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=str(_frontend_dist / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        fp = _frontend_dist / full_path
        if fp.exists() and fp.is_file():
            return FileResponse(str(fp))
        return FileResponse(str(_frontend_dist / "index.html"))


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    session = session_manager.create()
    session.ws_connected = True

    try:
        await websocket.send_json({
            "type": "session_started",
            "session_id": session.session_id,
        })

        output_task = asyncio.create_task(_forward_outputs(websocket, session))

        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "start":
                mode = data.get("mode", "new")
                params = data.get("params", {})
                thread = threading.Thread(
                    target=_run_pipeline,
                    args=(session, mode, params),
                    daemon=True,
                )
                session.thread = thread
                thread.start()

            elif msg_type == "input_response":
                session.input_queue.put(data)

            elif msg_type == "cancel":
                session.cancelled.set()

    except WebSocketDisconnect:
        session.ws_connected = False
        session.cancelled.set()
    finally:
        output_task.cancel()
        session_manager.remove(session.session_id)


async def _forward_outputs(websocket: WebSocket, session: BridgeSession):
    """将 output_queue 中的消息异步转发给 WebSocket。"""
    loop = asyncio.get_event_loop()
    while session.ws_connected:
        try:
            msg = await loop.run_in_executor(None, session.output_queue.get, True, 0.1)
        except queue.Empty:
            await asyncio.sleep(0.05)
            continue
        if msg is None:
            break
        try:
            await websocket.send_json(msg)
        except Exception:
            break


def _format_user_error(exc: Exception) -> str:
    """将技术异常转为用户可理解的中文错误消息。"""
    msg = str(exc)
    cls = type(exc).__name__

    # JSON 解析失败（LLM 输出截断或格式异常）
    if "Failed to parse JSON" in msg:
        return "AI 返回的数据格式异常（输出可能被截断），请尝试重新运行。"

    # API 连接错误
    if "ConnectionError" in cls or "APIConnectionError" in cls:
        return "网络连接失败，请检查网络后重试。"

    # API 限流
    if "RateLimitError" in cls or "rate_limit" in msg.lower() or "429" in msg:
        return "API 调用频率超限，请等待几分钟后重试。"

    # API 认证错误
    if "401" in msg or "authentication" in msg.lower():
        return "API Token 无效或已过期，请检查环境变量配置。"

    # API 服务器错误
    if "500" in msg or "502" in msg or "503" in msg:
        return "API 服务端暂时不可用，请稍后重试。"

    # 超时
    if "timeout" in msg.lower() or "timed out" in msg.lower():
        return "请求超时（AI 响应时间过长），请尝试减少章节数或重试。"

    # Token 额度
    if "quota" in msg.lower() or "billing" in msg.lower():
        return "API 额度不足，请检查账户余额。"

    # 通用兜底
    return f"运行出错（{cls}），请尝试重新运行。"


def _run_pipeline(session: BridgeSession, mode: str, params: dict):
    """在后台线程中运行 pipeline。"""
    set_current_session(session)

    try:
        if mode == "new":
            from core.braindump import braindump, extract_negative_constraints
            from core.pipeline import NovelPipeline

            idea = params.get("story_idea", "")
            name = params.get("novel_name", "untitled")
            style = params.get("style") or None

            enriched_idea = braindump(idea, name, style)
            style = extract_negative_constraints(enriched_idea, style)

            pipeline = NovelPipeline()
            pipeline.start_new_novel(enriched_idea, name, style=style)

        elif mode == "continue":
            from core.pipeline import NovelPipeline
            pipeline = NovelPipeline()
            pipeline.resume_novel(params.get("novel_name"))

        elif mode == "revise":
            from core.pipeline import NovelPipeline
            pipeline = NovelPipeline()
            pipeline.revise_chapter(
                params.get("novel_name"),
                params.get("chapter_number"),
            )

        session.output_queue.put({
            "type": "session_ended",
            "session_id": session.session_id,
            "reason": "completed",
        })

    except WebUserAbort:
        session.output_queue.put({
            "type": "session_ended",
            "session_id": session.session_id,
            "reason": "cancelled",
        })

    except _PhaseHandledError as e:
        # Phase handler 已展示过错误，只需发送 session_ended
        error_msg = _format_user_error(e.original)
        session.output_queue.put({
            "type": "session_ended",
            "session_id": session.session_id,
            "reason": "error",
            "error": error_msg,
        })

    except Exception as e:
        import traceback
        traceback.print_exc()

        # 将技术异常转为用户友好的错误消息
        error_msg = _format_user_error(e)

        # 通过 ui.error 发到前端消息流（用户能在日志中看到）
        try:
            from core import ui
            ui.error(error_msg)
            ui.hint("可以尝试重新运行，如果持续失败请检查网络或减少章节数。")
        except Exception:
            pass

        session.output_queue.put({
            "type": "session_ended",
            "session_id": session.session_id,
            "reason": "error",
            "error": error_msg,
        })
