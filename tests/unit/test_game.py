import asyncio

import pytest

from app import game as game_module
from app.game import Game
from tests.helpers import TEST_SET, make_set

pytestmark = pytest.mark.anyio


@pytest.fixture
def game() -> Game:
    return Game()


async def make_game(*players: str, start: bool = True) -> Game:
    game = Game(TEST_SET)
    for player in players:
        await game.join(player)
    if start:
        await game.next_question()
    return game


async def buzz_and_answer(game: Game, player: str, answer: str = "Paris") -> None:
    assert await game.buzz(player)
    assert await game.submit_answer(player, answer)


async def test_new_game_is_empty(game):
    assert game.players == {}
    assert game.chat_messages == []
    assert game.host is None
    assert game.current_winner is None
    assert game.current_answer is None
    assert game.current_lossers == []
    assert game.last_result is None
    assert game.phase == "lobby"
    assert not game.started
    assert not game.buzzing_open
    assert game.chat_open


async def test_join_adds_player_with_zero_points(game):
    await game.join("alice")
    assert game.players == {"alice": 0}


async def test_rejoining_keeps_score():
    game = await make_game("alice")
    await buzz_and_answer(game, "alice")
    await game.mark_correct()

    await game.join("alice")

    assert game.players["alice"] == 1


async def test_chat_records_sender_and_message(game):
    await game.add_chat_message("alice", "hi")
    assert game.chat_messages == [{"player": "alice", "message": "hi"}]


async def test_chat_keeps_only_last_50_messages(game):
    for i in range(60):
        await game.add_chat_message("alice", str(i))
    assert len(game.chat_messages) == 50
    assert game.chat_messages[0]["message"] == "10"
    assert game.chat_messages[-1]["message"] == "59"


# --- question phase ---

async def test_buzz_rejected_before_first_question():
    game = await make_game("alice", start=False)
    assert await game.buzz("alice") is False
    assert game.current_winner is None


async def test_next_question_starts_game_and_opens_buzzing():
    game = await make_game("alice")
    assert game.phase == "question"
    assert game.started
    assert game.buzzing_open
    assert not game.chat_open


async def test_first_buzz_wins_and_starts_answering():
    game = await make_game("alice", "bob")

    assert await game.buzz("alice") is True
    assert await game.buzz("bob") is False

    assert game.current_winner == "alice"
    assert game.phase == "answering"
    assert not game.buzzing_open
    assert not game.chat_open


async def test_buzz_from_unknown_player_rejected():
    game = await make_game("alice")
    assert await game.buzz("mallory") is False
    assert game.current_winner is None
    assert game.buzzing_open


async def test_concurrent_buzzes_have_exactly_one_winner():
    names = [f"p{i}" for i in range(100)]
    game = await make_game(*names)

    results = await asyncio.gather(*(game.buzz(name) for name in names))

    assert results.count(True) == 1
    assert game.current_winner == names[results.index(True)]


# --- answering phase ---

async def test_buzz_sets_answer_deadline():
    game = await make_game("alice")
    await game.buzz("alice")
    assert game_module.ANSWER_SECONDS - 1 < game.seconds_left() <= game_module.ANSWER_SECONDS


async def test_seconds_left_is_zero_without_deadline(game):
    assert game.seconds_left() == 0


async def test_each_buzz_gets_a_new_round():
    game = await make_game("alice", "bob")
    await game.buzz("alice")
    first = game.answer_round
    await game.submit_answer("alice", "x")
    await game.mark_wrong()
    await game.buzz("bob")
    assert game.answer_round != first


async def test_winner_submits_answer_for_judging():
    game = await make_game("alice")
    await game.buzz("alice")

    assert await game.submit_answer("alice", "Paris") is True

    assert game.phase == "judging"
    assert game.current_answer == "Paris"
    assert game.seconds_left() == 0


async def test_non_winner_cannot_answer():
    game = await make_game("alice", "bob")
    await game.buzz("alice")
    assert await game.submit_answer("bob", "Paris") is False
    assert game.phase == "answering"
    assert game.current_answer is None


async def test_blank_answer_rejected():
    game = await make_game("alice")
    await game.buzz("alice")
    assert await game.submit_answer("alice", "") is False
    assert game.phase == "answering"


@pytest.mark.parametrize("setup", ["lobby", "question", "judging", "intermission"])
async def test_answer_rejected_outside_answering(setup):
    game = await make_game("alice", start=setup != "lobby")
    if setup in ("judging", "intermission"):
        await buzz_and_answer(game, "alice", "first")
    if setup == "intermission":
        await game.mark_correct()

    assert await game.submit_answer("alice", "second") is False
    assert game.phase == setup


async def test_expiry_counts_as_wrong_and_reopens_buzzing():
    game = await make_game("alice", "bob")
    await game.buzz("alice")

    assert await game.expire_answer(game.answer_round) is True

    assert game.phase == "question"
    assert game.current_lossers == ["alice"]
    assert game.current_winner is None
    assert game.last_result == {"player": "alice", "answer": None, "correct": False}
    assert game.players["alice"] == 0
    assert await game.buzz("bob") is True


async def test_expiry_after_submit_does_nothing():
    game = await make_game("alice")
    await game.buzz("alice")
    answer_round = game.answer_round
    await game.submit_answer("alice", "Paris")

    assert await game.expire_answer(answer_round) is False
    assert game.phase == "judging"


async def test_stale_round_expiry_does_nothing():
    game = await make_game("alice", "bob")
    await game.buzz("alice")
    stale = game.answer_round
    await game.next_question()  # reveal
    await game.next_question()  # second question
    await game.buzz("bob")

    assert await game.expire_answer(stale) is False
    assert game.current_winner == "bob"
    assert game.phase == "answering"


async def test_rounds_are_unique_across_games():
    first, second = await make_game("alice"), await make_game("alice")
    await first.buzz("alice")
    await second.buzz("alice")
    assert first.answer_round != second.answer_round


async def test_expiry_after_reset_does_nothing():
    game = await make_game("alice")
    await game.buzz("alice")
    answer_round = game.answer_round
    await game.reset()

    assert await game.expire_answer(answer_round) is False
    assert game.phase == "lobby"


# --- judging ---

async def test_mark_correct_scores_and_starts_intermission():
    game = await make_game("alice")
    await buzz_and_answer(game, "alice", "Paris")

    await game.mark_correct()

    assert game.players["alice"] == 1
    assert game.phase == "intermission"
    assert game.current_winner is None
    assert game.last_result == {"player": "alice", "answer": "Paris", "correct": True}
    assert not game.buzzing_open
    assert game.chat_open


async def test_mark_correct_twice_only_scores_once():
    game = await make_game("alice")
    await buzz_and_answer(game, "alice")
    await game.mark_correct()

    with pytest.raises(RuntimeError):
        await game.mark_correct()
    assert game.players["alice"] == 1


@pytest.mark.parametrize("action", ["mark_correct", "mark_wrong"])
async def test_judging_without_answer_raises(action):
    game = await make_game("alice")
    with pytest.raises(RuntimeError):
        await getattr(game, action)()

    await game.buzz("alice")  # buzzed but still typing
    with pytest.raises(RuntimeError):
        await getattr(game, action)()
    assert game.players["alice"] == 0
    assert game.phase == "answering"


async def test_mark_wrong_locks_out_and_reopens_buzzing():
    game = await make_game("alice", "bob")
    await buzz_and_answer(game, "alice", "Lyon")

    await game.mark_wrong()

    assert game.phase == "question"
    assert game.current_lossers == ["alice"]
    assert game.current_winner is None
    assert game.current_answer is None
    assert game.last_result == {"player": "alice", "answer": "Lyon", "correct": False}
    assert game.players["alice"] == 0
    assert await game.buzz("alice") is False
    assert await game.buzz("bob") is True


async def test_everyone_wrong_leaves_nobody_able_to_buzz():
    game = await make_game("alice", "bob")
    for player in ("alice", "bob"):
        await buzz_and_answer(game, player)
        await game.mark_wrong()

    assert await game.buzz("alice") is False
    assert await game.buzz("bob") is False
    assert game.phase == "question"


async def test_skipping_live_question_reveals_then_moves_on():
    game = await make_game("alice", "bob")
    await buzz_and_answer(game, "alice")
    await game.mark_wrong()
    await game.buzz("bob")

    await game.next_question()

    assert game.phase == "reveal"
    assert game.question_index == 0  # still showing the skipped question's answer
    assert game.current_winner is None
    assert game.current_answer is None
    assert game.current_lossers == []
    assert game.last_result is None
    assert game.chat_open

    await game.next_question()

    assert game.phase == "question"
    assert game.question_index == 1
    assert await game.buzz("alice") is True


async def test_next_question_from_intermission():
    game = await make_game("alice")
    await buzz_and_answer(game, "alice")
    await game.mark_correct()

    await game.next_question()

    assert game.phase == "question"
    assert game.last_result is None


async def test_scores_accumulate_across_questions():
    game = await make_game("alice", "bob")
    for winner in ("alice", "bob", "alice"):
        await buzz_and_answer(game, winner)
        await game.mark_correct()
        await game.next_question()
    assert game.players == {"alice": 2, "bob": 1}


async def test_reset_clears_game_but_keeps_host():
    game = await make_game("alice")
    game.host = "Quizmaster"
    await game.add_chat_message("alice", "hi")
    await buzz_and_answer(game, "alice")

    await game.reset()

    assert game.players == {}
    assert game.chat_messages == []
    assert game.current_winner is None
    assert game.current_answer is None
    assert game.current_lossers == []
    assert game.last_result is None
    assert game.phase == "lobby"
    assert game.host == "Quizmaster"


async def test_players_from_before_reset_cannot_buzz():
    game = await make_game("alice")
    await game.reset()
    await game.next_question()

    assert await game.buzz("alice") is False
    assert game.current_winner is None


# --- question sets ---

async def test_game_starts_on_first_question():
    game = await make_game("alice")
    assert game.question_index == 0
    assert game.current_question == TEST_SET.questions[0]


async def test_lobby_has_no_current_question():
    game = await make_game("alice", start=False)
    assert game.current_question is None


async def test_cannot_start_without_a_question_set():
    game = Game()
    await game.join("alice")
    await game.next_question()
    assert game.phase == "lobby"


async def test_load_questions_in_lobby():
    game = Game()
    other = make_set("other", [{"question": "Q?", "answer": "A"}])
    assert await game.load_questions(other) is True
    assert game.question_set is other
    await game.next_question()
    assert game.current_question.question == "Q?"


@pytest.mark.parametrize("phase", ["question", "answering", "intermission", "game_over"])
async def test_load_questions_refused_mid_game(phase):
    game = await make_game("alice")
    if phase in ("answering", "intermission"):
        await game.buzz("alice")
    if phase == "intermission":
        await game.submit_answer("alice", "x")
        await game.mark_correct()
    if phase == "game_over":
        game.phase = "game_over"

    assert await game.load_questions(make_set("other")) is False
    assert game.question_set is TEST_SET


async def test_questions_asked_in_file_order_then_game_over():
    game = await make_game("alice")
    asked = []
    while game.phase != "game_over":
        asked.append(game.current_question.answer)
        await buzz_and_answer(game, "alice")
        await game.mark_correct()
        assert game.is_last_question == (len(asked) == 3)
        await game.next_question()

    assert asked == ["ANSWER-ONE", "ANSWER-TWO", "ANSWER-THREE"]
    assert game.current_question is None
    assert game.players["alice"] == 3
    assert game.chat_open


async def test_skipping_every_question_reaches_game_over():
    game = await make_game("alice")
    for _ in range(3):
        await game.next_question()  # reveal
        assert game.phase == "reveal"
        await game.next_question()
    assert game.phase == "game_over"


async def test_next_does_nothing_after_game_over():
    game = await make_game("alice")
    game.phase = "game_over"
    game.question_index = 3
    await game.next_question()
    assert game.phase == "game_over"
    assert game.question_index == 3


async def test_buzz_rejected_during_reveal_and_game_over():
    game = await make_game("alice")
    await game.next_question()  # reveal
    assert await game.buzz("alice") is False
    game.phase = "game_over"
    assert await game.buzz("alice") is False


async def test_reset_rewinds_to_first_question_and_keeps_set():
    game = await make_game("alice")
    await game.next_question()
    await game.next_question()
    await game.reset()

    assert game.question_index == -1
    assert game.question_set is TEST_SET
    await game.next_question()
    assert game.current_question == TEST_SET.questions[0]


async def test_reset_can_swap_in_reloaded_set():
    game = await make_game("alice")
    reloaded = make_set("test-set", [{"question": "Edited?", "answer": "Yes"}])
    await game.reset(reloaded)
    assert game.question_set is reloaded


@pytest.mark.parametrize("scores, winners", [
    ({}, []),
    ({"alice": 0, "bob": 0}, []),
    ({"alice": 2, "bob": 1}, ["alice"]),
    ({"alice": 2, "bob": 2, "carol": 1}, ["alice", "bob"]),
])
async def test_winners(game, scores, winners):
    game.players = dict(scores)
    assert game.winners() == winners
