import pytest

from app.main import render_screen
from tests.helpers import TEST_SET, buzz_enabled, leaderboard, make_set, screen_of, text

LIVE = ("question", "answering", "judging")

CORRECT = {"player": "bob", "answer": "Paris", "correct": True}
WRONG = {"player": "bob", "answer": "Lyon", "correct": False}
TIMED_OUT = {"player": "bob", "answer": None, "correct": False}


def context(**overrides) -> dict:
    values = dict(
        phase="question",
        players={"alice": 0, "bob": 0},
        current_winner=None,
        current_answer=None,
        current_lossers=[],
        last_result=None,
        seconds_left=15,
        chat_messages=[{"player": "bob", "message": "gg"}],
        question_set=TEST_SET,
        question=TEST_SET.questions[0],
        question_number=1,
        question_count=3,
        is_last_question=False,
        winners=[],
        sets=[TEST_SET],
        question_error=None,
    )
    values.update(overrides)
    values.setdefault("chat_open", values["phase"] not in LIVE)
    return values


def game_screen(**overrides) -> str:
    return render_screen("game.html", **context(**{"player": "alice", **overrides}))


def host_screen(**overrides) -> str:
    return render_screen("host_controls.html", **context(**{"host": "Quizmaster", **overrides}))


# every partial is swapped in out-of-band, so it must target the right element id
@pytest.mark.parametrize("html, target", [
    (render_screen("join.html"), "screen"),
    (render_screen("lobby.html", players={}, chat_messages=[]), "screen"),
    (game_screen(), "screen"),
    (render_screen("start_game.html"), "host_screen"),
    (host_screen(), "host_screen"),
], ids=["join", "lobby", "game", "start_game", "host_controls"])
def test_partials_swap_into_correct_element(html, target):
    assert html.lstrip().startswith(f'<div id="{target}" hx-swap-oob="true">')


def test_join_screen_without_error():
    html = render_screen("join.html")
    assert screen_of(html) == "join"
    assert 'id="player"' in html
    assert "error" not in html


def test_join_screen_shows_error():
    html = render_screen("join.html", error="That name is already taken.")
    assert "That name is already taken." in text(html)


def test_lobby_lists_players_and_chat():
    html = render_screen(
        "lobby.html",
        players={"alice": 0, "bob": 0},
        chat_messages=[{"player": "alice", "message": "hello"}],
    )
    assert screen_of(html) == "lobby"
    assert "alice" in html and "bob" in html
    assert "alice: hello" in text(html)
    assert 'hx-vals=\'{"type": "chat"}\'' in html


# --- player game screen ---

@pytest.mark.parametrize("phase", ["question", "answering", "judging", "intermission"])
def test_game_shows_player_and_score(phase):
    html = game_screen(
        phase=phase, players={"alice": 3, "bob": 0}, current_winner="bob",
        current_answer="Paris", last_result=CORRECT,
    )
    assert screen_of(html) == "game"
    assert "Playing as alice — 3 points" in text(html)


@pytest.mark.parametrize("phase", ["question", "answering", "judging"])
def test_game_hides_chat_and_leaderboard_during_question(phase):
    html = game_screen(phase=phase, current_winner="bob", current_answer="Paris")
    assert 'id="leaderboard"' not in html
    assert 'id="chat-form"' not in html
    assert "bob: gg" not in text(html)


def test_game_question_buzzing_open():
    html = game_screen()
    assert "Buzz in!" in html
    assert buzz_enabled(html)
    assert "or press Space" in html


def test_game_question_buzz_button_sends_buzz():
    assert 'id="buzz-button" ws-send hx-vals=\'{"type": "buzz"}\'' in game_screen()


def test_game_question_locked_out():
    html = game_screen(current_lossers=["alice"])
    assert "locked out" in html
    assert not buzz_enabled(html)


def test_game_question_other_player_locked_out_can_still_buzz():
    html = game_screen(current_lossers=["bob"])
    assert "Buzz in!" in html
    assert buzz_enabled(html)


def test_game_question_shows_last_wrong_guess():
    assert 'bob guessed "Lyon" — wrong' in text(game_screen(last_result=WRONG, current_lossers=["bob"]))


def test_game_question_shows_timeout():
    assert "bob ran out of time" in text(game_screen(last_result=TIMED_OUT, current_lossers=["bob"]))


def test_game_question_without_last_result():
    assert "last-result" not in game_screen()


def test_game_answering_winner_gets_answer_form():
    html = game_screen(phase="answering", current_winner="alice", seconds_left=12)
    assert "You buzzed in first!" in html
    assert '<form id="answer-form" ws-send hx-vals=\'{"type": "answer"}\'>' in html
    assert 'name="answer"' in html
    assert 'maxlength="100"' in html
    assert 'data-seconds-left="12"' in html
    assert 'id="buzz-button"' not in html


def test_game_answering_others_wait_with_countdown():
    html = game_screen(phase="answering", current_winner="bob", seconds_left=9)
    assert "bob is answering" in html
    assert 'id="answer-form"' not in html
    assert 'class="countdown" data-seconds-left="9"' in html


def test_game_judging_shows_answer_to_everyone():
    for player in ("alice", "bob"):
        html = render_screen("game.html", **context(
            player=player, phase="judging", current_winner="bob", current_answer="Paris",
        ))
        assert 'bob answered: "Paris"' in text(html)
        assert 'id="answer-form"' not in html


def test_game_intermission_shows_result_leaderboard_and_chat():
    html = game_screen(phase="intermission", last_result=CORRECT, players={"alice": 1, "bob": 5, "carol": 3})
    assert "bob got it!" in text(html)
    assert 'bob said "Paris"' in text(html)
    assert "Answer: ANSWER-ONE" in text(html)
    assert leaderboard(html) == ["bob — 5", "carol — 3", "alice — 1"]
    assert "bob: gg" in text(html)
    assert 'id="chat-form"' in html
    assert 'id="buzz-button"' not in html


# --- host panel ---

def test_start_game_asks_for_host_name():
    html = render_screen("start_game.html")
    assert screen_of(html) == "host_start"
    assert 'id="host"' in html
    assert 'ws-send hx-vals=\'{"type": "host_join"}\'' in html


def test_host_shows_name_and_player_count():
    html = host_screen()
    assert screen_of(html) == "host"
    assert "Hosting as Quizmaster" in text(html)
    assert "Leaderboard (2 players)" in text(html)


def test_host_lobby_says_start_game():
    html = host_screen(phase="lobby")
    assert 'hx-vals=\'{"type": "next"}\'>Start game</button>' in html
    assert "Next question" not in html


@pytest.mark.parametrize("phase", LIVE)
def test_host_says_reveal_answer_during_live_question(phase):
    html = host_screen(phase=phase, current_winner="bob", current_answer="Paris")
    assert 'hx-vals=\'{"type": "next"}\'>Reveal answer</button>' in html


@pytest.mark.parametrize("phase", ["intermission", "reveal"])
def test_host_says_next_question_between_questions(phase):
    html = host_screen(phase=phase, last_result=CORRECT)
    assert 'hx-vals=\'{"type": "next"}\'>Next question</button>' in html
    assert "Start game" not in html


@pytest.mark.parametrize("phase", ["intermission", "reveal"])
def test_host_says_final_results_after_last_question(phase):
    html = host_screen(phase=phase, last_result=CORRECT, is_last_question=True)
    assert 'hx-vals=\'{"type": "next"}\'>Final results</button>' in html


@pytest.mark.parametrize("phase", ["lobby", "question", "answering", "judging", "intermission"])
def test_host_always_shows_leaderboard(phase):
    html = host_screen(phase=phase, current_winner="bob", current_answer="Paris", last_result=CORRECT)
    assert 'id="leaderboard"' in html


@pytest.mark.parametrize("phase, chat_visible", [
    ("lobby", True), ("question", False), ("answering", False), ("judging", False),
    ("intermission", True), ("reveal", True), ("game_over", True),
])
def test_host_chat_only_between_questions(phase, chat_visible):
    html = host_screen(phase=phase, current_winner="bob", current_answer="Paris", last_result=CORRECT)
    assert ('id="chat-form"' in html) is chat_visible


@pytest.mark.parametrize("phase", ["lobby", "question", "answering", "intermission"])
def test_host_correct_and_wrong_hidden_unless_judging(phase):
    html = host_screen(phase=phase, current_winner="bob", last_result=CORRECT)
    assert '"type": "correct"' not in html
    assert '"type": "wrong"' not in html


def test_host_judging_shows_answer_with_correct_and_wrong():
    html = host_screen(phase="judging", current_winner="bob", current_answer="Paris")
    assert 'bob answered: "Paris"' in text(html)
    assert '"type": "correct"' in html
    assert '"type": "wrong"' in html


def test_host_question_status():
    assert "Buzzing is open" in host_screen()


def test_host_answering_shows_countdown():
    html = host_screen(phase="answering", current_winner="bob", seconds_left=7)
    assert "bob is answering" in text(html)
    assert 'class="countdown" data-seconds-left="7"' in html


def test_host_shows_last_wrong_guess_and_timeout():
    assert 'bob guessed "Lyon" — wrong' in text(host_screen(last_result=WRONG))
    assert "bob ran out of time" in text(host_screen(last_result=TIMED_OUT))


def test_host_intermission_shows_who_got_it():
    assert 'bob got it! ("Paris")' in text(host_screen(phase="intermission", last_result=CORRECT))


def test_host_lists_locked_out_players():
    html = host_screen(current_lossers=["alice", "bob"])
    assert "Locked out: alice, bob" in text(html)


def test_host_reset_asks_for_confirmation():
    assert "hx-confirm=" in host_screen()


def test_host_leaderboard_sorted_by_score():
    html = host_screen(players={"alice": 1, "bob": 5})
    assert leaderboard(html) == ["bob — 5", "alice — 1"]


EVIL = '<script>alert("x")</script>'
EVIL_RESULT = {"player": EVIL, "answer": EVIL, "correct": True}


@pytest.mark.parametrize("html", [
    render_screen("lobby.html", players={EVIL: 0}, chat_messages=[{"player": EVIL, "message": EVIL}]),
    game_screen(player=EVIL, players={EVIL: 0}, phase="intermission", last_result=EVIL_RESULT,
                chat_messages=[{"player": EVIL, "message": EVIL}]),
    game_screen(phase="judging", current_winner=EVIL, current_answer=EVIL),
    game_screen(phase="answering", current_winner=EVIL),
    game_screen(last_result={**EVIL_RESULT, "correct": False}),
    host_screen(host=EVIL, players={EVIL: 0}, phase="judging", current_winner=EVIL, current_answer=EVIL,
                current_lossers=[EVIL]),
    host_screen(phase="intermission", last_result=EVIL_RESULT, chat_messages=[{"player": EVIL, "message": EVIL}]),
    render_screen("join.html", error=EVIL),
], ids=["lobby", "game-intermission", "game-judging", "game-answering", "game-wrong",
        "host-judging", "host-intermission", "join"])
def test_user_text_is_html_escaped(html):
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


# --- questions and answers ---

@pytest.mark.parametrize("phase", LIVE)
@pytest.mark.parametrize("player", ["alice", "bob"])
def test_players_see_question_but_never_answer_while_live(phase, player):
    html = game_screen(player=player, phase=phase, current_winner="bob", current_answer="typed")
    assert "First test question?" in html
    assert "Question 1 of 3" in text(html)
    assert "ANSWER-ONE" not in html


@pytest.mark.parametrize("phase", ["intermission", "reveal"])
def test_players_see_official_answer_between_questions(phase):
    html = game_screen(phase=phase, last_result=CORRECT)
    assert "ANSWER-ONE" in html
    assert 'class="answer-reveal"' in html
    assert "First test question?" not in html


def test_reveal_screen():
    html = game_screen(phase="reveal")
    assert "Nobody got it" in html
    assert "The answer was: ANSWER-ONE" in text(html)
    assert 'id="leaderboard"' in html and 'id="chat-form"' in html
    assert "Waiting for the next question" in html


@pytest.mark.parametrize("winners, headline", [
    (["bob"], "Game over — bob wins!"),
    (["alice", "bob"], "Game over — alice and bob tie!"),
    ([], "Game over — nobody scored!"),
])
def test_game_over_screen(winners, headline):
    html = game_screen(phase="game_over", question=None, winners=winners, players={"alice": 1, "bob": 2})
    assert headline in text(html)
    assert leaderboard(html) == ["bob — 2", "alice — 1"]
    assert 'id="chat-form"' in html
    assert "Waiting for the next question" not in html
    assert 'id="buzz-button"' not in html


@pytest.mark.parametrize("phase", LIVE + ("intermission", "reveal"))
def test_host_always_sees_question_and_answer(phase):
    html = host_screen(phase=phase, current_winner="bob", current_answer="typed", last_result=CORRECT)
    assert "First test question?" in html
    assert "Answer: ANSWER-ONE" in text(html)
    assert "Test Set · Question 1 of 3" in text(html)


def test_host_lobby_hides_question():
    html = host_screen(phase="lobby")
    assert "First test question?" not in html
    assert "ANSWER-ONE" not in html


@pytest.mark.parametrize("winners, headline", [
    (["bob"], "Game over — bob wins!"),
    (["alice", "bob"], "Game over — alice and bob tie!"),
    ([], "Game over — nobody scored!"),
])
def test_host_game_over(winners, headline):
    html = host_screen(phase="game_over", question=None, winners=winners)
    assert headline in text(html)
    assert '"type": "next"' not in html
    assert '"type": "reset"' in html


def test_host_reveal_status():
    assert "Nobody got it" in host_screen(phase="reveal")


# --- question set picker ---

def test_lobby_shows_question_set():
    html = render_screen("lobby.html", players={}, chat_messages=[], question_set=TEST_SET)
    assert "Question set: Test Set (3 questions)" in text(html)


def test_lobby_without_question_set():
    html = render_screen("lobby.html", players={}, chat_messages=[], question_set=None)
    assert "Question set" not in html


def test_host_picker_lists_sets_with_current_selected():
    other = make_set("world-capitals", [{"question": "Q?", "answer": "A"}])
    html = host_screen(phase="lobby", sets=[TEST_SET, other])
    assert '<form id="set-form" ws-send hx-vals=\'{"type": "choose_set"}\'>' in html
    assert 'name="question_set"' in html
    assert '<option value="test-set" selected>' in html
    assert '<option value="world-capitals">' in html
    assert "World Capitals (1 questions)" in text(html)
    assert "Loaded: Test Set (3 questions)" in text(html)


def test_host_picker_disables_broken_sets_and_lists_errors():
    from app.questions import QuestionSet
    broken = QuestionSet("broken", "Broken", error="broken.json: invalid JSON (oops on line 1)")
    html = host_screen(phase="lobby", sets=[TEST_SET, broken])
    assert '<option value="broken" disabled>' in html
    assert "Broken (broken)" in text(html)
    assert "broken.json: invalid JSON (oops on line 1)" in text(html)


def test_host_without_any_sets_cannot_start():
    html = host_screen(phase="lobby", sets=[], question_set=None, question=None)
    assert 'id="set-form"' not in html
    assert "No question sets found" in text(html)
    assert '<button disabled ws-send hx-vals=\'{"type": "next"}\'>Start game</button>' in html


def test_host_picker_only_in_lobby():
    assert 'id="set-form"' not in host_screen(phase="question")


def test_host_shows_question_error_banner():
    html = host_screen(question_error="That question set wasn't found.")
    assert '<p class="error">That question set wasn&#39;t found.</p>' in html


def test_question_and_set_text_is_escaped():
    evil = '<script>alert("x")</script>'
    evil_set = make_set("evil", [{"question": evil, "answer": evil}])
    for html in (
        game_screen(question=evil_set.questions[0]),
        game_screen(phase="reveal", question=evil_set.questions[0]),
        host_screen(question_set=evil_set, question=evil_set.questions[0]),
    ):
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
