"""FastAPI 应用：WebSocket 端点 + REST API + Vue SPA 静态文件。"""

import asyncio
import queue
import signal
import threading

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# 关键：在导入 pipeline 之前安装桥接层
from web.bridge import install_web_bridge
install_web_bridge()

from web.bridge.session import BridgeSession, session_manager
from web.bridge.web_prompt import set_current_session, WebUserAbort
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


def _run_pipeline(session: BridgeSession, mode: str, params: dict):
    """在后台线程中运行 pipeline。"""
    set_current_session(session)

    try:
        if mode == "new":
            from main import _braindump, _extract_negative_constraints
            from core.pipeline import NovelPipeline

            idea = params.get("story_idea", "")
            name = params.get("novel_name", "untitled")
            style = params.get("style") or None

            # braindump
            enriched_idea = _braindump(idea, name, style)
            style = _extract_negative_constraints(enriched_idea, style)

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

    except Exception as e:
        import traceback
        traceback.print_exc()
        session.output_queue.put({
            "type": "session_ended",
            "session_id": session.session_id,
            "reason": "error",
            "error": str(e),
        })
