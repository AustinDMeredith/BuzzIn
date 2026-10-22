import asyncio
import logging

# init logger for module
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class Game:
    """Shared trivia state: players, scores, and the first-buzz-wins lock."""

    def __init__(self) -> None:
        self._buzz_lock = asyncio.Lock()
        self.buzzing_open: bool = False
        self.players: dict[str, int] = {}
        self.current_winner: str | None = None
        self.current_lossers: list[str] = []
        self.chat_messages: list[dict[str, str]] = []
        # TODO: current question state, locked-out players, scoring rules

    async def join(self, player: str) -> None:
        self.players[player] = 0
        logger.debug(f"{player} has joined the game!")

    async def add_chat_message(self, player: str, message: str) -> None:
        self.chat_messages.append({"player": player, "message": message})
        self.chat_messages = self.chat_messages[-50:]

    async def buzz(self, player: str) -> bool:
        """Attempt to claim the buzz lock. Returns True if this player is the first-in."""
        # TODO: under self._buzz_lock, set current_winner once per question
        async with self._buzz_lock:
            if not self.buzzing_open:
                return False
            if player in self.current_lossers:
                return False
            self.current_winner = player
            self.buzzing_open = False
            return True

    async def next_question(self) -> None:
        # TODO: advance to next question, clear current_winner, reopen buzzing
        self.current_winner = None
        self.current_lossers.clear()
        self.buzzing_open = True
        raise NotImplementedError

    async def mark_correct(self, player: str) -> None:
        # TODO: increment player's score
        raise NotImplementedError

    async def mark_wrong(self, player: str) -> None:
        self.current_winner = None
        self.current_lossers.append(player)

        # TODO: reopen buzzing without advancing the question
        raise NotImplementedError

    async def reset(self) -> None:
        # TODO: clear players/scores and restart the game
        raise NotImplementedError
