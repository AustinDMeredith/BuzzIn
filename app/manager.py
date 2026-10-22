import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Tracks connected sockets and broadcasts HTML fragments for HTMX to swap in."""

    def __init__(self) -> None:
        self.active_connections: dict[str, WebSocket] = {}
        self.host: WebSocket | None = None

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()

    def register(self, player: str, websocket: WebSocket) -> None:
        self.active_connections[player] = websocket

    def register_host(self, websocket: WebSocket) -> None:
        self.host = websocket

    def is_registered(self, player: str, websocket: WebSocket) -> bool:
        return self.active_connections.get(player) is websocket

    def disconnect(self, player: str, websocket: WebSocket) -> None:
        # only drop the player if this socket still owns the name
        if self.is_registered(player, websocket):
            del self.active_connections[player]

    def disconnect_host(self, websocket: WebSocket) -> None:
        if self.host is websocket:
            self.host = None

    async def _send(self, websocket: WebSocket, html_fragment: str) -> bool:
        """Send to one socket, returning False if it has gone away."""
        try:
            await websocket.send_text(html_fragment)
            return True
        except Exception as exc:
            logger.debug(f"dropping dead socket: {exc!r}")
            return False

    async def broadcast(self, html_fragment: str) -> None:
        for player, connection in list(self.active_connections.items()):
            if not await self._send(connection, html_fragment):
                self.disconnect(player, connection)

    async def send_to(self, player: str, html_fragment: str) -> None:
        websocket = self.active_connections.get(player)
        if websocket and not await self._send(websocket, html_fragment):
            self.disconnect(player, websocket)

    async def send_host(self, html_fragment: str) -> None:
        host = self.host
        if host and not await self._send(host, html_fragment):
            self.disconnect_host(host)
