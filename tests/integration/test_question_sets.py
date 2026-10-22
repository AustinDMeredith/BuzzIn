import json

import pytest

from app import main
from tests.helpers import leaderboard, screen_of, text

pytestmark = pytest.mark.anyio

CAPITALS = [
    {"question": "Capital of Japan?", "answer": "Tokyo"},
    {"question": "Capital of Peru?", "answer": "Lima"},
]


def write_set(folder, set_id, questions):
    (folder / f"{set_id}.json").write_text(json.dumps(questions) if not isinstance(questions, str) else questions)


@pytest.fixture
async def lobby(room, questions_dir):
    """Host plus alice in the lobby, with a second set (capitals) available."""
    write_set(questions_dir, "capitals", CAPITALS)
    await room.add_host()
    await room.add_player("alice")
    return room


async def test_host_sees_every_set_in_the_folder(lobby):
    html = lobby.last["host"]
    assert '<option value="capitals">' in html
    assert '<option value="test-set" selected>' in html
    assert "Capitals (2 questions)" in text(html)


async def test_host_picks_set_and_players_lobby_updates(lobby):
    await lobby.host.send("choose_set", question_set="capitals")
    updates = await lobby.collect()

    assert "Question set: Capitals (2 questions)" in text(updates["alice"])
    assert "Loaded: Capitals (2 questions)" in text(updates["host"])
    assert '<option value="capitals" selected>' in updates["host"]
    assert main.game.question_set.id == "capitals"


async def test_chosen_set_is_played(lobby):
    await lobby.host.send("choose_set", question_set="capitals")
    await lobby.collect()

    updates = await lobby.next()

    assert "Capital of Japan?" in updates["alice"]
    assert "Answer: Tokyo" in text(updates["host"])
    assert "Tokyo" not in updates["alice"]


@pytest.mark.parametrize("set_id", ["nope", "../app/main", "../../etc/passwd", "test-set.json", "", None, 7, ["capitals"]])
async def test_unknown_or_malicious_set_id_is_rejected(lobby, set_id):
    await lobby.host.send("choose_set", question_set=set_id)

    updates = await lobby.collect_from("host")

    assert "That question set wasn&#39;t found." in updates["host"]
    assert main.game.question_set.id == "test-set"


async def test_choosing_broken_set_shows_its_error(lobby, questions_dir):
    write_set(questions_dir, "broken", "{")
    await lobby.host.send("choose_set", question_set="broken")

    updates = await lobby.collect_from("host")

    assert "broken.json: invalid JSON" in text(updates["host"])
    assert main.game.question_set.id == "test-set"


async def test_players_cannot_choose_set(lobby):
    await lobby["alice"].send("choose_set", question_set="capitals")
    await lobby.assert_silent()
    assert main.game.question_set.id == "test-set"


async def test_set_cannot_change_mid_game(lobby):
    await lobby.next()
    await lobby.host.send("choose_set", question_set="capitals")
    await lobby.assert_silent()
    assert main.game.question_set.id == "test-set"


async def test_load_rereads_edited_file(lobby, questions_dir):
    write_set(questions_dir, "capitals", CAPITALS + [{"question": "Capital of Chad?", "answer": "N'Djamena"}])
    await lobby.host.send("choose_set", question_set="capitals")
    updates = await lobby.collect()
    assert "Capitals (3 questions)" in text(updates["alice"])


async def test_new_file_shows_up_after_reset(lobby, questions_dir):
    write_set(questions_dir, "history", [{"question": "Q?", "answer": "A"}])
    await lobby.host.send("reset")
    updates = await lobby.collect()
    assert '<option value="history">' in updates["host"]


async def test_new_file_shows_up_when_host_reloads(room, questions_dir):
    await room.add_host()
    write_set(questions_dir, "history", [{"question": "Q?", "answer": "A"}])
    await room.leave("host")

    host = await room.connect()
    await host.send("host_join", host="Quizmaster")

    assert '<option value="history">' in await host.expect("host")


async def test_reset_rereads_current_set(lobby, questions_dir):
    await lobby.next()
    write_set(questions_dir, "test-set", [{"question": "Edited question?", "answer": "Edited"}])

    await lobby.host.send("reset")
    await lobby.collect()
    await lobby["alice"].send("join", player="alice")
    await lobby.collect()
    updates = await lobby.next()

    assert "Edited question?" in updates["alice"]


async def test_reset_keeps_old_copy_if_file_breaks(lobby, questions_dir):
    write_set(questions_dir, "test-set", "[oops")

    await lobby.host.send("reset")
    updates = await lobby.collect()

    assert "Couldn&#39;t reload Test Set" in updates["host"]
    assert main.game.question_set.questions[0].answer == "ANSWER-ONE"


async def test_reset_keeps_old_copy_if_file_is_deleted(lobby, questions_dir):
    (questions_dir / "test-set.json").unlink()

    await lobby.host.send("reset")
    updates = await lobby.collect()

    assert "Test Set was removed from the folder" in updates["host"]
    assert main.game.question_set.id == "test-set"


async def test_fixing_the_file_clears_the_error(lobby, questions_dir):
    write_set(questions_dir, "test-set", "[oops")
    await lobby.host.send("reset")
    await lobby.collect()

    write_set(questions_dir, "test-set", [{"question": "Fixed?", "answer": "Yes"}])
    await lobby.host.send("choose_set", question_set="test-set")
    updates = await lobby.collect_from("host")

    assert 'class="error"' not in updates["host"]


async def test_first_set_auto_loads_when_none_was_loaded(room, questions_dir, monkeypatch):
    main.game.__init__(None)
    monkeypatch.setattr(main, "question_sets", [])

    host = await room.connect()
    await host.send("host_join", host="Quizmaster")
    html = await host.expect("host")

    assert "Loaded: Test Set (3 questions)" in text(html)
    assert main.game.question_set.id == "test-set"


async def test_empty_folder_means_host_cannot_start(room, questions_dir, monkeypatch):
    (questions_dir / "test-set.json").unlink()
    main.game.__init__(None)
    monkeypatch.setattr(main, "question_sets", [])

    await room.add_host()
    await room.add_player("alice")
    assert "No question sets found" in text(room.last["host"])
    assert "<button disabled" in room.last["host"]

    await room.host.send("next")
    await room.collect()
    assert main.game.phase == "lobby"


async def test_full_game_through_every_question(lobby):
    await lobby.add_player("bob")
    await lobby.next()  # question 1

    await lobby.win("alice", "answer-one")
    assert "ANSWER-ONE" in lobby.last["bob"]
    await lobby.next()  # question 2

    assert "Second test question?" in lobby.last["bob"]
    await lobby.win("bob")
    await lobby.next()  # question 3

    await lobby.next()  # nobody got it: reveal
    assert "The answer was: ANSWER-THREE" in text(lobby.last["alice"])
    assert ">Final results</button>" in lobby.last["host"]

    updates = await lobby.next()

    assert main.game.phase == "game_over"
    for name in ("alice", "bob"):
        assert "Game over — alice and bob tie!" in text(updates[name])
        assert leaderboard(updates[name]) == ["alice — 1", "bob — 1"]
    assert '"type": "next"' not in updates["host"]

    # nothing moves past game over except reset
    await lobby.next()
    assert main.game.phase == "game_over"

    updates = await lobby.judge("reset")
    assert screen_of(updates["alice"]) == "join"
    assert ">Start game</button>" in updates["host"]
