import pytest

from app import main
from tests.helpers import buzz_enabled, leaderboard, screen_of, text

pytestmark = pytest.mark.anyio


async def test_host_join_shows_controls(room):
    host = await room.connect()
    await host.send("host_join", host="Quizmaster")
    html = await host.expect("host")
    assert "Hosting as Quizmaster" in text(html)
    assert main.game.host == "Quizmaster"


async def test_host_with_blank_name_is_called_host(room):
    host = await room.connect()
    await host.send("host_join", host="   ")
    assert "Hosting as Host" in text(await host.expect("host"))


async def test_host_name_is_trimmed_and_capped(room):
    host = await room.connect()
    await host.send("host_join", host="  " + "Q" * 100 + "  ")
    await host.expect("host")
    assert main.game.host == "Q" * main.MAX_NAME_LENGTH


async def test_player_join_shows_lobby_to_everyone(room):
    await room.add_host()
    await room.add_player("alice")
    await room.add_player("bob")

    assert screen_of(room.last["alice"]) == "lobby"
    assert screen_of(room.last["bob"]) == "lobby"
    assert "alice" in room.last["bob"] and "bob" in room.last["alice"]
    assert "Leaderboard (2 players)" in text(room.last["host"])
    assert main.game.players == {"alice": 0, "bob": 0}


async def test_players_can_join_without_a_host(room):
    await room.add_player("alice")
    assert screen_of(room.last["alice"]) == "lobby"


async def test_player_name_is_trimmed_and_capped(room):
    player = await room.connect()
    await player.send("join", player="  " + "a" * 100 + "  ")
    await player.expect("lobby")
    assert list(main.game.players) == ["a" * main.MAX_NAME_LENGTH]


@pytest.mark.parametrize("name", ["", "   ", None])
async def test_blank_name_is_rejected(room, name):
    await room.add_host()
    player = await room.connect()
    await player.send("join", player=name)

    html = await player.expect("join")

    assert "Enter a name to join." in text(html)
    assert main.game.players == {}
    await room.host.assert_silent()


async def test_missing_name_is_rejected(room):
    player = await room.connect()
    await player.send("join")
    assert "Enter a name to join." in text(await player.expect("join"))


async def test_name_taken_by_connected_player_is_rejected(room):
    await room.add_host()
    await room.add_player("alice")
    imposter = await room.connect()

    await imposter.send("join", player="alice")

    assert "That name is already taken." in text(await imposter.expect("join"))
    await room.assert_silent()


async def test_rejected_player_can_retry_with_another_name(room):
    await room.add_player("alice")
    player = await room.connect()
    await player.send("join", player="alice")
    await player.expect("join")

    room.clients["alice2"] = player
    await player.send("join", player="alice2")
    await room.collect()

    assert main.game.players == {"alice": 0, "alice2": 0}


async def test_name_hijack_does_not_steal_score(started_room):
    await started_room.win("alice")

    imposter = await started_room.connect()
    await imposter.send("join", player="alice")
    await imposter.expect("join")

    assert main.game.players["alice"] == 1
    assert main.manager.active_connections["alice"] is not None


async def test_second_join_from_same_socket_is_ignored(room):
    alice = await room.add_player("alice")
    await alice.send("join", player="alice-again")
    await alice.assert_silent()
    assert list(main.game.players) == ["alice"]


async def test_reconnecting_player_keeps_score(started_room):
    await started_room.win("alice")

    await started_room.leave("alice")
    await started_room.add_player("alice")

    assert main.game.players["alice"] == 1
    assert "Playing as alice — 1 points" in text(started_room.last["alice"])


async def test_late_joiner_lands_on_game_screen(started_room):
    await started_room.add_player("carol")  # also checks alice and bob get nothing
    assert screen_of(started_room.last["carol"]) == "game"
    assert buzz_enabled(started_room.last["carol"])
    assert "Leaderboard (3 players)" in text(started_room.last["host"])


async def test_late_joiner_does_not_wipe_answer_being_typed(started_room):
    await started_room.buzz("alice")

    await started_room.add_player("carol")  # alice must not get a fresh screen mid-typing

    assert "alice is answering" in started_room.last["carol"]
    assert main.game.phase == "answering"


async def test_late_joiner_during_intermission_updates_everyone(started_room):
    await started_room.win("alice")
    await started_room.add_player("carol")
    assert leaderboard(started_room.last["bob"]) == ["alice — 1", "bob — 0", "carol — 0"]


async def test_host_reload_restores_controls(room):
    await room.add_host()
    await room.add_player("alice")
    await room.leave("host")

    host = await room.connect()
    await host.send("host_join", host="Quizmaster")
    html = await host.expect("host")
    assert "Leaderboard (1 players)" in text(html)
