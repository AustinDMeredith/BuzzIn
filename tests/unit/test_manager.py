import pytest

from app.manager import ConnectionManager

pytestmark = pytest.mark.anyio


class FakeSocket:
    """Stands in for a WebSocket: records what was sent, or fails like a closed socket."""

    def __init__(self, broken: bool = False) -> None:
        self.accepted = False
        self.broken = broken
        self.sent: list[str] = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_text(self, text: str) -> None:
        if self.broken:
            raise RuntimeError('Cannot call "send" once a close message has been sent.')
        self.sent.append(text)


@pytest.fixture
def manager() -> ConnectionManager:
    return ConnectionManager()


async def test_connect_accepts_socket(manager):
    socket = FakeSocket()
    await manager.connect(socket)
    assert socket.accepted


async def test_broadcast_reaches_every_player_but_not_host(manager):
    alice, bob, host = FakeSocket(), FakeSocket(), FakeSocket()
    manager.register("alice", alice)
    manager.register("bob", bob)
    manager.register_host(host)

    await manager.broadcast("<p>hi</p>")

    assert alice.sent == ["<p>hi</p>"]
    assert bob.sent == ["<p>hi</p>"]
    assert host.sent == []


async def test_broadcast_with_no_players_is_a_no_op(manager):
    await manager.broadcast("<p>hi</p>")


async def test_send_to_targets_one_player(manager):
    alice, bob = FakeSocket(), FakeSocket()
    manager.register("alice", alice)
    manager.register("bob", bob)

    await manager.send_to("alice", "<p>hi</p>")

    assert alice.sent == ["<p>hi</p>"]
    assert bob.sent == []


async def test_send_to_unknown_player_is_a_no_op(manager):
    await manager.send_to("nobody", "<p>hi</p>")


async def test_send_host(manager):
    host = FakeSocket()
    manager.register_host(host)
    await manager.send_host("<p>hi</p>")
    assert host.sent == ["<p>hi</p>"]


async def test_send_host_without_host_is_a_no_op(manager):
    await manager.send_host("<p>hi</p>")


async def test_register_same_name_replaces_socket(manager):
    old, new = FakeSocket(), FakeSocket()
    manager.register("alice", old)
    manager.register("alice", new)

    await manager.broadcast("<p>hi</p>")

    assert old.sent == []
    assert new.sent == ["<p>hi</p>"]


async def test_is_registered_checks_name_and_socket(manager):
    alice, other = FakeSocket(), FakeSocket()
    manager.register("alice", alice)

    assert manager.is_registered("alice", alice)
    assert not manager.is_registered("alice", other)
    assert not manager.is_registered("bob", alice)


async def test_disconnect_removes_player(manager):
    alice = FakeSocket()
    manager.register("alice", alice)
    manager.disconnect("alice", alice)
    assert "alice" not in manager.active_connections


async def test_disconnect_ignores_socket_that_no_longer_owns_name(manager):
    old, new = FakeSocket(), FakeSocket()
    manager.register("alice", old)
    manager.register("alice", new)

    manager.disconnect("alice", old)

    assert manager.active_connections["alice"] is new


async def test_disconnect_unknown_player_is_a_no_op(manager):
    manager.disconnect("nobody", FakeSocket())


async def test_disconnect_host_only_clears_matching_socket(manager):
    old, new = FakeSocket(), FakeSocket()
    manager.register_host(old)
    manager.register_host(new)

    manager.disconnect_host(old)
    assert manager.host is new

    manager.disconnect_host(new)
    assert manager.host is None


async def test_broadcast_skips_and_drops_dead_socket(manager):
    alice, dead, bob = FakeSocket(), FakeSocket(broken=True), FakeSocket()
    manager.register("alice", alice)
    manager.register("dead", dead)
    manager.register("bob", bob)

    await manager.broadcast("<p>hi</p>")

    assert alice.sent == ["<p>hi</p>"]
    assert bob.sent == ["<p>hi</p>"]
    assert "dead" not in manager.active_connections


async def test_send_to_dead_socket_drops_it(manager):
    manager.register("dead", FakeSocket(broken=True))
    await manager.send_to("dead", "<p>hi</p>")
    assert "dead" not in manager.active_connections


async def test_send_host_to_dead_socket_clears_host(manager):
    manager.register_host(FakeSocket(broken=True))
    await manager.send_host("<p>hi</p>")
    assert manager.host is None
