import asyncio
import contextlib
import json
import socket
import threading
import time

import pytest
import uvicorn
import websockets

from app import main
from app.main import app
from tests.helpers import screen_of, wait_until

RECV_TIMEOUT = 2.0
SILENCE_WINDOW = 0.3


@pytest.fixture(scope="session")
def server_url():
    """Run the real app under uvicorn in a background thread for the whole test session."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("uvicorn did not start")
        time.sleep(0.05)

    yield f"ws://127.0.0.1:{port}/ws"

    server.should_exit = True
    thread.join(timeout=5)


class Client:
    """One browser tab's WebSocket, with helpers for the HTML fragments the server pushes."""

    def __init__(self, ws) -> None:
        self.ws = ws

    async def send(self, type: str, **fields) -> None:
        await self.ws.send(json.dumps({"type": type, **fields}))

    async def send_raw(self, data: str | bytes) -> None:
        await self.ws.send(data)

    async def recv(self) -> str:
        return await asyncio.wait_for(self.ws.recv(), RECV_TIMEOUT)

    async def expect(self, screen: str) -> str:
        html = await self.recv()
        assert screen_of(html) == screen, html
        return html

    async def assert_silent(self) -> None:
        with pytest.raises(TimeoutError):
            message = await asyncio.wait_for(self.ws.recv(), SILENCE_WINDOW)
            pytest.fail(f"expected no message, got:\n{message}")

    async def close(self) -> None:
        await self.ws.close()


class Room:
    """A host plus players, with helpers to drain the update every action fans out to everyone."""

    def __init__(self, connect) -> None:
        self.connect = connect
        self.clients: dict[str, Client] = {}
        self.last: dict[str, str] = {}

    async def add_host(self, name: str = "Quizmaster") -> Client:
        host = await self.connect()
        await host.send("host_join", host=name)
        await host.expect("host")
        self.clients["host"] = host
        return host

    async def add_player(self, name: str) -> Client:
        player = await self.connect()
        self.clients[name] = player
        await player.send("join", player=name)
        if main.game.chat_open:
            await self.collect()
        else:
            # mid-question only the joiner and the host hear about it
            await self.collect_from(*[n for n in (name, "host") if n in self.clients])
        return player

    async def buzz(self, name: str) -> dict[str, str]:
        """A buzz that's expected to win."""
        await self[name].send("buzz")
        return await self.collect()

    async def answer(self, name: str, answer: str = "Paris") -> dict[str, str]:
        await self[name].send("answer", answer=answer)
        return await self.collect()

    async def judge(self, verdict: str) -> dict[str, str]:
        await self.host.send(verdict)
        return await self.collect()

    async def next(self) -> dict[str, str]:
        return await self.judge("next")

    async def win(self, name: str, answer: str = "Paris") -> dict[str, str]:
        """Buzz, answer and get marked correct, landing everyone in intermission."""
        await self.buzz(name)
        await self.answer(name, answer)
        return await self.judge("correct")

    async def collect(self) -> dict[str, str]:
        """Receive exactly one message on every client in the room."""
        names = list(self.clients)
        htmls = await asyncio.gather(*(self.clients[name].recv() for name in names))
        self.last = dict(zip(names, htmls))
        return self.last

    async def collect_from(self, *names: str) -> dict[str, str]:
        """Receive one message on just the named clients, then check the rest heard nothing."""
        htmls = await asyncio.gather(*(self.clients[name].recv() for name in names))
        others = [client for name, client in self.clients.items() if name not in names]
        await asyncio.gather(*(client.assert_silent() for client in others))
        self.last = dict(zip(names, htmls))
        return self.last

    async def assert_silent(self) -> None:
        await asyncio.gather(*(client.assert_silent() for client in self.clients.values()))

    async def leave(self, name: str) -> None:
        """Close a client and wait until the server has finished cleaning it up."""
        client = self.clients.pop(name)
        socket = client.ws
        await client.close()
        if name == "host":
            await wait_until(lambda: main.manager.host is None)
        else:
            await wait_until(lambda: name not in main.manager.active_connections)
        assert socket.close_code is not None

    @property
    def host(self) -> Client:
        return self.clients["host"]

    def __getitem__(self, name: str) -> Client:
        return self.clients[name]


@pytest.fixture
async def connect(server_url):
    async with contextlib.AsyncExitStack() as stack:
        async def _connect() -> Client:
            return Client(await stack.enter_async_context(websockets.connect(server_url)))
        yield _connect


@pytest.fixture
async def room(connect) -> Room:
    return Room(connect)


@pytest.fixture
async def started_room(room) -> Room:
    """A host with alice and bob, on the first question with buzzing open."""
    await room.add_host()
    await room.add_player("alice")
    await room.add_player("bob")
    await room.host.send("next")
    await room.collect()
    return room
