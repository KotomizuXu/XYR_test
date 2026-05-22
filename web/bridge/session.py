"""会话管理：每个 pipeline 运行在独立线程中，通过队列与 WebSocket 通信。"""

import queue
import threading
import uuid
from dataclasses import dataclass, field


@dataclass
class BridgeSession:
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    output_queue: queue.Queue = field(default_factory=queue.Queue)
    input_queue: queue.Queue = field(default_factory=queue.Queue)
    thread: threading.Thread | None = None
    cancelled: threading.Event = field(default_factory=threading.Event)
    novel_name: str | None = None
    ws_connected: bool = False


class SessionManager:
    def __init__(self):
        self._sessions: dict[str, BridgeSession] = {}
        self._lock = threading.Lock()

    def create(self) -> BridgeSession:
        session = BridgeSession()
        with self._lock:
            self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> BridgeSession | None:
        return self._sessions.get(session_id)

    def remove(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)


session_manager = SessionManager()
