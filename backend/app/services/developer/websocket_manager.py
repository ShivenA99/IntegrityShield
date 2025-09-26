from __future__ import annotations

from typing import Dict

from flask_sock import ConnectionClosed


class WebsocketManager:
    def __init__(self) -> None:
        self.connections: Dict[str, list] = {}

    def register(self, run_id: str, socket) -> None:
        self.connections.setdefault(run_id, []).append(socket)

    def unregister(self, run_id: str, socket) -> None:
        if run_id in self.connections and socket in self.connections[run_id]:
            self.connections[run_id].remove(socket)

    def broadcast(self, run_id: str, payload: dict) -> None:
        sockets = self.connections.get(run_id, [])
        for ws in list(sockets):
            try:
                ws.send_json(payload)
            except ConnectionClosed:
                self.unregister(run_id, ws)


websocket_manager = WebsocketManager()
