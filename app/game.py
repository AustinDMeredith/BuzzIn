import asyncio


class Game:
    """Shared trivia state: players, scores, and the first-buzz-wins lock."""

    def __init__(self) -> None:
        self._buzz_lock = asyncio.Lock()
        self.players: dict[str, int] = {}
        self.current_winner: str | None = None
        # TODO: current question state, locked-out players, scoring rules

    async def join(self, player: str) -> None:
        # TODO: register a new player with score 0
        raise NotImplementedError

    async def buzz(self, player: str) -> bool:
        """Attempt to claim the buzz lock. Returns True if this player is the first-in."""
        # TODO: under self._buzz_lock, set current_winner once per question
        raise NotImplementedError

    async def next_question(self) -> None:
        # TODO: advance to next question, clear current_winner, reopen buzzing
        raise NotImplementedError

    async def mark_correct(self, player: str) -> None:
        # TODO: increment player's score
        raise NotImplementedError

    async def mark_wrong(self, player: str) -> None:
        # TODO: reopen buzzing without advancing the question
        raise NotImplementedError

    async def reset(self) -> None:
        # TODO: clear players/scores and restart the game
        raise NotImplementedError
