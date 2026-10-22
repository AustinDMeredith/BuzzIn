from fastapi import WebSocket


class ConnectionManager:
    """Tracks connected sockets and broadcasts HTML fragments for HTMX to swap in."""

    def __init__(self) -> None:
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()

    def register(self, player: str, websocket: WebSocket) -> None:
        self.active_connections[player] = websocket

    def disconnect(self, player: str) -> None:
        self.active_connections.pop(player, None)

    async def broadcast(self, html_fragment: str) -> None:
        for connection in self.active_connections.values():
            await connection.send_text(html_fragment)

    async def send_to(self, player: str, html_fragment: str) -> None:
        websocket = self.active_connections.get(player)
        if websocket:
            await websocket.send_text(html_fragment)
