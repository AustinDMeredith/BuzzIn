import asyncio

import pytest

from app import game as game_module
from app import main
from tests.helpers import buzz_enabled, leaderboard, screen_of, text

pytestmark = pytest.mark.anyio


@pytest.fixture
def short_timer(monkeypatch):
    monkeypatch.setattr(game_module, "ANSWER_SECONDS", 0.3)


async def test_host_starts_game_from_lobby(room):
    await room.add_host()
    await room.add_player("alice")
    assert ">Start game</button>" in room.last["host"]

    updates = await room.next()

    assert screen_of(updates["alice"]) == "game"
    assert ">Reveal answer</button>" in updates["host"]


async def test_question_shows_buzzer_without_chat_or_leaderboard(started_room):
    for name in ("alice", "bob"):
        html = started_room.last[name]
        assert screen_of(html) == "game"
        assert "Buzz in!" in html
        assert buzz_enabled(html)
        assert 'id="chat-form"' not in html
        assert 'id="leaderboard"' not in html
    assert "Buzzing is open" in started_room.last["host"]
    assert 'id="leaderboard"' in started_room.last["host"]


async def test_buzz_before_first_question_is_ignored(room):
    await room.add_host()
    alice = await room.add_player("alice")

    await alice.send("buzz")

    await room.assert_silent()
    assert main.game.current_winner is None


async def test_first_buzz_gets_answer_box_others_see_countdown(started_room):
    updates = await started_room.buzz("bob")

    assert 'id="answer-form"' in updates["bob"]
    assert "bob is answering" in updates["alice"]
    assert 'id="answer-form"' not in updates["alice"]
    assert 'class="countdown"' in updates["alice"]
    assert "bob is answering" in text(updates["host"])
    assert '"type": "correct"' not in updates["host"]  # nothing to judge yet
    assert main.game.phase == "answering"


async def test_second_buzz_after_winner_is_ignored(started_room):
    await started_room.buzz("bob")
    await started_room["alice"].send("buzz")
    await started_room.assert_silent()
    assert main.game.current_winner == "bob"


async def test_answer_is_broadcast_to_everyone(started_room):
    await started_room.buzz("bob")

    updates = await started_room.answer("bob", "Paris")

    for name in ("alice", "bob", "host"):
        assert 'bob answered: "Paris"' in text(updates[name])
    assert '"type": "correct"' in updates["host"]
    assert '"type": "wrong"' in updates["host"]


@pytest.mark.parametrize("answer", ["", "   ", None])
async def test_blank_answer_is_ignored(started_room, answer):
    await started_room.buzz("bob")
    await started_room["bob"].send("answer", answer=answer)
    await started_room.assert_silent()
    assert main.game.phase == "answering"


async def test_answer_missing_field_is_ignored(started_room):
    await started_room.buzz("bob")
    await started_room["bob"].send("answer")
    await started_room.assert_silent()


async def test_long_answer_is_capped(started_room):
    await started_room.buzz("bob")
    await started_room.answer("bob", "x" * 5000)
    assert main.game.current_answer == "x" * main.MAX_ANSWER_LENGTH


async def test_answer_html_is_escaped(started_room):
    await started_room.buzz("bob")
    updates = await started_room.answer("bob", "<img src=x onerror=alert(1)>")
    for html in updates.values():
        assert "<img" not in html


async def test_non_winner_cannot_answer(started_room):
    await started_room.buzz("bob")
    await started_room["alice"].send("answer", answer="Paris")
    await started_room.assert_silent()
    assert main.game.current_answer is None


async def test_answer_without_buzzing_is_ignored(started_room):
    await started_room["alice"].send("answer", answer="Paris")
    await started_room.assert_silent()
    assert main.game.phase == "question"


async def test_second_answer_is_ignored(started_room):
    await started_room.buzz("bob")
    await started_room.answer("bob", "Paris")
    await started_room["bob"].send("answer", answer="Lyon")
    await started_room.assert_silent()
    assert main.game.current_answer == "Paris"


async def test_correct_starts_intermission_with_chat_and_leaderboard(started_room):
    updates = await started_room.win("alice", "Paris")

    assert main.game.players == {"alice": 1, "bob": 0}
    assert main.game.phase == "intermission"
    assert "Playing as alice — 1 points" in text(updates["alice"])
    for name in ("alice", "bob"):
        assert "alice got it!" in text(updates[name])
        assert 'id="chat-form"' in updates[name]
        assert leaderboard(updates[name]) == ["alice — 1", "bob — 0"]
    assert 'alice got it! ("Paris")' in text(updates["host"])
    assert 'id="chat-form"' in updates["host"]
    assert '"type": "correct"' not in updates["host"]


async def test_correct_twice_only_scores_once(started_room):
    await started_room.win("alice")
    await started_room.judge("correct")
    assert main.game.players["alice"] == 1


@pytest.mark.parametrize("action", ["correct", "wrong"])
async def test_judging_before_any_buzz_is_harmless(started_room, action):
    updates = await started_room.judge(action)
    assert main.game.players == {"alice": 0, "bob": 0}
    assert main.game.current_lossers == []
    assert screen_of(updates["host"]) == "host"


@pytest.mark.parametrize("action", ["correct", "wrong"])
async def test_judging_while_still_typing_is_ignored(started_room, action):
    await started_room.buzz("alice")
    await started_room.judge(action)
    assert main.game.phase == "answering"
    assert main.game.players["alice"] == 0


async def test_wrong_locks_out_shows_guess_and_reopens_for_others(started_room):
    await started_room.buzz("alice")
    await started_room.answer("alice", "Lyon")

    updates = await started_room.judge("wrong")

    for name in ("alice", "bob", "host"):
        assert 'alice guessed "Lyon" — wrong' in text(updates[name])
    assert "locked out" in updates["alice"]
    assert not buzz_enabled(updates["alice"])
    assert buzz_enabled(updates["bob"])
    assert "Locked out: alice" in text(updates["host"])
    assert 'id="chat-form"' not in updates["bob"]


async def test_locked_out_player_cannot_buzz(started_room):
    await started_room.buzz("alice")
    await started_room.answer("alice", "Lyon")
    await started_room.judge("wrong")

    await started_room["alice"].send("buzz")

    await started_room.assert_silent()
    assert main.game.current_winner is None


async def test_other_player_can_buzz_and_win_after_wrong_answer(started_room):
    await started_room.buzz("alice")
    await started_room.answer("alice", "Lyon")
    await started_room.judge("wrong")

    await started_room.win("bob")

    assert main.game.players == {"alice": 0, "bob": 1}


async def test_everyone_wrong_leaves_buzzer_dead_until_next(started_room):
    for name in ("alice", "bob"):
        await started_room.buzz(name)
        await started_room.answer(name, "nope")
        await started_room.judge("wrong")

    for name in ("alice", "bob"):
        assert not buzz_enabled(started_room.last[name])
        await started_room[name].send("buzz")
    await started_room.assert_silent()

    await started_room.next()  # reveal the answer
    updates = await started_room.next()
    assert buzz_enabled(updates["alice"]) and buzz_enabled(updates["bob"])


async def test_next_clears_lockouts_and_last_guess(started_room):
    await started_room.buzz("alice")
    await started_room.answer("alice", "Lyon")
    await started_room.judge("wrong")

    await started_room.next()  # reveal the answer
    updates = await started_room.next()

    assert main.game.current_lossers == []
    assert "guessed" not in updates["alice"]
    assert "You buzzed in first!" in (await started_room.buzz("alice"))["alice"]


@pytest.mark.parametrize("stage", ["answering", "judging"])
async def test_host_can_skip_mid_turn(started_room, stage):
    await started_room.buzz("alice")
    if stage == "judging":
        await started_room.answer("alice")

    reveal = await started_room.next()
    for name in ("alice", "bob"):
        assert "Nobody got it" in reveal[name]
        assert "ANSWER-ONE" in reveal[name]

    updates = await started_room.next()

    assert main.game.players == {"alice": 0, "bob": 0}
    assert buzz_enabled(updates["alice"]) and buzz_enabled(updates["bob"])


async def test_full_game_scores(started_room):
    for winner in ("alice", "bob", "alice"):
        await started_room.win(winner)
        await started_room.next()

    assert main.game.players == {"alice": 2, "bob": 1}
    assert leaderboard(started_room.last["host"]) == ["alice — 2", "bob — 1"]


async def test_simultaneous_buzzes_have_one_winner(room):
    await room.add_host()
    names = [f"p{i}" for i in range(20)]
    for name in names:
        await room.add_player(name)
    await room.next()

    await asyncio.gather(*(room[name].send("buzz") for name in names))
    updates = await room.collect()
    await room.assert_silent()

    winners = [name for name in names if 'id="answer-form"' in updates[name]]
    assert winners == [main.game.current_winner]
    assert f"{winners[0]} is answering" in text(updates["host"])


# --- answer timer ---

async def test_timeout_counts_as_wrong_and_reopens_buzzing(started_room, short_timer):
    await started_room.buzz("alice")

    updates = await started_room.collect()  # pushed by the timer, nobody did anything

    for name in ("alice", "bob", "host"):
        assert "alice ran out of time" in text(updates[name])
    assert "locked out" in updates["alice"]
    assert buzz_enabled(updates["bob"])
    assert main.game.current_lossers == ["alice"]
    assert main.game.players["alice"] == 0


async def test_answering_in_time_cancels_timeout(started_room, short_timer):
    await started_room.buzz("alice")
    await started_room.answer("alice", "Paris")

    await started_room.assert_silent()  # outlasts the 0.3s timer
    assert main.game.phase == "judging"
    assert main.game.current_lossers == []


async def test_answer_after_timeout_is_ignored(started_room, short_timer):
    await started_room.buzz("alice")
    await started_room.collect()  # timed out

    await started_room["alice"].send("answer", answer="Paris")
    await started_room.assert_silent()
    assert main.game.current_answer is None


@pytest.mark.parametrize("action", ["next", "reset"])
async def test_old_timer_is_harmless_after_next_or_reset(started_room, short_timer, action):
    await started_room.buzz("alice")
    await started_room.judge(action)

    await started_room.assert_silent()
    assert main.game.current_lossers == []


async def test_timer_after_new_buzz_only_affects_new_round(started_room, monkeypatch):
    monkeypatch.setattr(game_module, "ANSWER_SECONDS", 0.5)
    await started_room.buzz("alice")
    await started_room.next()  # reveal
    await started_room.next()  # second question
    monkeypatch.setattr(game_module, "ANSWER_SECONDS", 15)
    await started_room.buzz("bob")

    await started_room.assert_silent()  # alice's 0.5s timer fires here and must do nothing
    await asyncio.sleep(0.3)
    assert main.game.current_winner == "bob"
    assert main.game.phase == "answering"


async def test_winner_disconnecting_times_out(started_room, short_timer):
    await started_room.buzz("bob")
    await started_room.leave("bob")

    updates = await started_room.collect()

    assert "bob ran out of time" in text(updates["alice"])
    assert buzz_enabled(updates["alice"])


# --- reset ---

async def test_reset_sends_players_back_to_join(started_room):
    await started_room.win("alice")

    updates = await started_room.judge("reset")

    assert screen_of(updates["alice"]) == "join"
    assert screen_of(updates["bob"]) == "join"
    assert "Leaderboard (0 players)" in text(updates["host"])
    assert ">Start game</button>" in updates["host"]
    assert main.game.players == {}
    assert main.manager.active_connections == {}


async def test_stale_player_cannot_buzz_answer_or_chat_after_reset(started_room):
    await started_room.judge("reset")
    await started_room.host.send("next")
    await started_room.host.recv()

    await started_room["alice"].send("buzz")
    await started_room["alice"].send("answer", answer="Paris")
    await started_room["alice"].send("chat", message="still here?")
    await started_room.assert_silent()
    assert main.game.current_winner is None
    assert main.game.chat_messages == []

    # judging after stale attempts must not crash the host
    await started_room.host.send("correct")
    assert screen_of(await started_room.host.recv()) == "host"


async def test_players_rejoin_after_reset_with_fresh_scores(started_room):
    await started_room.win("alice")
    await started_room.judge("reset")

    await started_room["alice"].send("join", player="alice")
    updates = await started_room.collect_from("alice", "host")

    assert screen_of(updates["alice"]) == "lobby"
    assert main.game.players == {"alice": 0}
