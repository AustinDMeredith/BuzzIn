import pytest

from loadtest import bots
from loadtest.bots import Round, Stats

pytestmark = pytest.mark.anyio


async def test_bots_play_a_full_game(server_url):
    stats = await bots.run(server_url, 5, delays=(0, 0.05))

    assert stats.failures() == []
    assert stats.connected == stats.held == stats.server_players == 5
    assert stats.game_over
    # every bot answer is marked correct, so each of the 3 test questions is exactly one round
    assert sorted(stats.rounds) == [(1, 1), (2, 1), (3, 1)]
    for round_ in stats.rounds.values():
        assert len(round_.claims) == 1
        assert round_.seen == set(round_.claims)


async def test_bots_report_a_bad_set_id(server_url):
    stats = await bots.run(server_url, 2, set_id="no-such-set")

    assert stats.connected == 0
    assert "couldn't load question set 'no-such-set'" in stats.host_error


@pytest.mark.parametrize("round_, ok", [
    (Round(claims=["bot-01"], seen={"bot-01"}), True),
    (Round(claims=["bot-01", "bot-02"], seen={"bot-01", "bot-02"}), False),
    (Round(claims=["bot-01"], seen={"bot-01", "bot-02"}), False),
    (Round(claims=[], seen={"a human"}), True),
])
def test_round_needs_exactly_one_winner(round_, ok):
    assert round_.ok is ok


def test_failures_flag_two_winners():
    stats = Stats(2, hosted=False, connected=2, rounds={(1, 1): Round(["bot-01", "bot-02"], {"bot-01", "bot-02"})})
    assert stats.failures() == ["question 1 round 1 had winners ['bot-01', 'bot-02']"]
