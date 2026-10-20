from fastapi import WebSocket


class ConnectionManager:
    """Tracks connected sockets and broadcasts HTML fragments for HTMX to swap in."""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self.active_connections.remove(websocket)

    async def broadcast(self, html_fragment: str) -> None:
        for connection in self.active_connections:
            await connection.send_text(html_fragment)
