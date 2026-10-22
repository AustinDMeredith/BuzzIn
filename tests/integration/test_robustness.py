"""Bad input, dropped connections and odd timing must never break the game for anyone else."""
import json

import pytest

from app import main
from tests.helpers import screen_of, text, wait_until

pytestmark = pytest.mark.anyio

BAD_FRAMES = [
    "not json",
    "{",
    "",
    b"\x00\x01binary",
    json.dumps([1, 2, 3]),
    json.dumps("join"),
    json.dumps(42),
    json.dumps(None),
    json.dumps({}),
    json.dumps({"type": None}),
    json.dumps({"type": 7}),
    json.dumps({"type": ["join"]}),
    json.dumps({"type": "launch_missiles"}),
]


@pytest.mark.parametrize("frame", BAD_FRAMES, ids=repr)
async def test_bad_frame_is_ignored_and_socket_keeps_working(room, frame):
    await room.add_host()
    alice = await room.add_player("alice")

    await alice.send_raw(frame)
    await room.assert_silent()

    await alice.send("chat", message="still alive")
    updates = await room.collect()
    assert "alice: still alive" in text(updates["alice"])


@pytest.mark.parametrize("frame", BAD_FRAMES, ids=repr)
async def test_bad_frame_before_join_does_not_block_joining(room, frame):
    player = await room.connect()
    await player.send_raw(frame)
    await player.send("join", player="alice")
    await player.expect("lobby")


@pytest.mark.parametrize("fields", [
    {"player": 123},
    {"player": {"nested": "dict"}},
    {"player": ["a", "b"]},
])
async def test_non_string_name_does_not_crash(room, fields):
    player = await room.connect()
    await player.send("join", **fields)
    assert screen_of(await player.recv()) in ("lobby", "join")
    await player.send("chat", message="ok")
    await player.recv()


@pytest.mark.parametrize("message", ["", "   ", None])
async def test_blank_chat_is_ignored(room, message):
    await room.add_host()
    alice = await room.add_player("alice")
    await alice.send("chat", message=message)
    await room.assert_silent()
    assert main.game.chat_messages == []


async def test_chat_without_message_field_is_ignored(room):
    alice = await room.add_player("alice")
    await alice.send("chat")
    await room.assert_silent()


async def test_long_chat_is_capped(room):
    alice = await room.add_player("alice")
    await alice.send("chat", message="x" * 10_000)
    await room.collect()
    assert main.game.chat_messages[0]["message"] == "x" * main.MAX_CHAT_LENGTH


async def test_htmx_headers_field_is_tolerated(room):
    # htmx-ext-ws adds a HEADERS object to every ws-send message
    alice = await room.add_player("alice")
    await alice.send("chat", message="hi", HEADERS={"HX-Request": "true", "HX-Trigger": "chat-form"})
    updates = await room.collect()
    assert "alice: hi" in text(updates["alice"])


async def test_chat_html_is_escaped(room):
    await room.add_host()
    alice = await room.add_player("alice")
    await alice.send("chat", message="<img src=x onerror=alert(1)>")
    updates = await room.collect()
    for html in updates.values():
        assert "<img" not in html
        assert "&lt;img" in html


async def test_host_chat_is_sent_under_host_name(room):
    await room.add_host()
    await room.add_player("alice")
    await room.host.send("chat", message="good luck")
    updates = await room.collect()
    assert "Quizmaster: good luck" in text(updates["alice"])


@pytest.mark.parametrize("stage", ["question", "answering", "judging"])
@pytest.mark.parametrize("sender", ["bob", "host"])
async def test_chat_is_ignored_while_question_is_up(started_room, stage, sender):
    if stage != "question":
        await started_room.buzz("alice")
    if stage == "judging":
        await started_room.answer("alice")

    await started_room.clients[sender].send("chat", message="psst")

    await started_room.assert_silent()
    assert main.game.chat_messages == []


async def test_chat_works_during_intermission(started_room):
    await started_room.win("alice")

    await started_room["bob"].send("chat", message="gg")
    updates = await started_room.collect()

    assert screen_of(updates["alice"]) == "game"
    assert "bob: gg" in text(updates["alice"])
    assert "bob: gg" in text(updates["host"])


async def test_player_leaving_mid_game_does_not_break_others(started_room):
    await started_room.leave("bob")

    await started_room["alice"].send("buzz")
    updates = await started_room.collect()

    assert "You buzzed in first!" in updates["alice"]
    assert "bob" in main.game.players  # still on the leaderboard


async def test_winner_leaving_can_still_be_judged(started_room):
    await started_room.buzz("bob")
    await started_room.answer("bob")
    await started_room.leave("bob")

    await started_room.host.send("correct")
    await started_room.collect()

    assert main.game.players["bob"] == 1


async def test_host_leaving_does_not_break_players(started_room):
    await started_room.leave("host")

    await started_room["alice"].send("buzz")
    updates = await started_room.collect()
    assert "You buzzed in first!" in updates["alice"]


async def test_dead_socket_in_manager_does_not_block_broadcast(started_room):
    class DeadSocket:
        async def send_text(self, text):
            raise RuntimeError('Cannot call "send" once a close message has been sent.')

    main.manager.register("ghost", DeadSocket())

    await started_room["alice"].send("buzz")
    updates = await started_room.collect()

    assert "You buzzed in first!" in updates["alice"]
    assert "alice is answering" in updates["bob"]
    assert "ghost" not in main.manager.active_connections


async def test_abrupt_disconnect_is_cleaned_up(started_room):
    bob = started_room.clients.pop("bob")
    bob.ws.transport.abort()  # drop TCP with no close frame, like a phone losing signal

    await wait_until(lambda: "bob" not in main.manager.active_connections)

    await started_room["alice"].send("buzz")
    updates = await started_room.collect()
    assert "You buzzed in first!" in updates["alice"]


async def test_server_survives_many_connect_disconnect_cycles(room):
    await room.add_host()
    for i in range(25):
        player = await room.connect()
        await player.send("join", player=f"p{i}")
        await player.expect("lobby")
        await room.host.expect("host")
        await player.close()

    await room.add_player("last")
    assert screen_of(room.last["last"]) == "lobby"
