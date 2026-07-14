from fastapi import WebSocket

class ProgressManager:
    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, task_id: str, ws: WebSocket):
        await ws.accept()
        self._connections.setdefault(task_id, []).append(ws)

    def disconnect(self, task_id: str, ws: WebSocket):
        conns = self._connections.get(task_id, [])
        if ws in conns:
            conns.remove(ws)

    async def send_progress(self, task_id: str, data: dict):
        for ws in self._connections.get(task_id, []):
            try:
                await ws.send_json(data)
            except Exception:
                pass

progress_manager = ProgressManager()
