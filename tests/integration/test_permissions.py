import pytest

from app import main
from tests.helpers import screen_of, text

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize("action", ["next", "correct", "wrong", "reset"])
async def test_players_cannot_use_host_controls(started_room, action):
    await started_room["alice"].send("buzz")
    await started_room.collect()

    await started_room["bob"].send(action)

    await started_room.assert_silent()
    assert main.game.current_winner == "alice"
    assert main.game.players == {"alice": 0, "bob": 0}


@pytest.mark.parametrize("action", ["next", "correct", "wrong", "reset"])
async def test_unjoined_socket_cannot_use_host_controls(started_room, action):
    stranger = await started_room.connect()
    await stranger.send(action)
    await stranger.assert_silent()
    await started_room.assert_silent()


async def test_unjoined_socket_cannot_buzz(started_room):
    stranger = await started_room.connect()
    await stranger.send("buzz")
    await stranger.assert_silent()
    await started_room.assert_silent()
    assert main.game.current_winner is None


async def test_unjoined_socket_cannot_chat(room):
    await room.add_player("alice")
    stranger = await room.connect()
    await stranger.send("chat", message="hi")
    await stranger.assert_silent()
    await room.assert_silent()
    assert main.game.chat_messages == []


async def test_new_host_takes_over_and_old_host_loses_control(started_room):
    old_host = started_room.host
    new_host = await started_room.connect()
    await new_host.send("host_join", host="Second")
    await new_host.expect("host")
    started_room.clients["host"] = new_host

    await old_host.send("next")
    await old_host.send("reset")
    await old_host.assert_silent()
    await started_room.assert_silent()
    assert main.game.players == {"alice": 0, "bob": 0}

    await new_host.send("next")
    updates = await started_room.collect()
    assert "Hosting as Second" in text(updates["host"])


async def test_old_host_leaving_does_not_unseat_new_host(started_room):
    old_host = started_room.host
    new_host = await started_room.connect()
    await new_host.send("host_join", host="Second")
    await new_host.expect("host")
    started_room.clients["host"] = new_host

    await old_host.close()
    await new_host.send("next")
    updates = await started_room.collect()

    assert screen_of(updates["host"]) == "host"
    assert main.manager.host is not None
