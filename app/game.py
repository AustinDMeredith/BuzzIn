import asyncio
import itertools
import logging
import time

from app.questions import Question, QuestionSet

# init logger for module
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# how long the first player in has to type their answer
ANSWER_SECONDS = 15.0

# unique across every Game, so a timer from an old round can never match a new one
_answer_rounds = itertools.count(1)


class Game:
    """Shared trivia state: players, scores, and the first-buzz-wins lock.

    phase moves lobby -> question -> answering -> judging -> intermission -> question ...
    A wrong or timed-out answer sends judging/answering back to question. The host skipping
    a live question shows its answer (reveal), and running out of questions ends the game.
    """

    LIVE_PHASES = ("question", "answering", "judging")

    def __init__(self, question_set: QuestionSet | None = None) -> None:
        self._buzz_lock = asyncio.Lock()
        self.host: str | None = None
        self.phase: str = "lobby"
        self.question_set: QuestionSet | None = question_set
        self.question_index: int = -1
        self.players: dict[str, int] = {}
        self.current_winner: str | None = None
        self.current_answer: str | None = None
        self.current_lossers: list[str] = []
        self.last_result: dict | None = None
        self.answer_round: int = 0
        self.answer_deadline: float | None = None
        self.chat_messages: list[dict[str, str]] = []

    @property
    def started(self) -> bool:
        return self.phase != "lobby"

    @property
    def buzzing_open(self) -> bool:
        return self.phase == "question"

    @property
    def chat_open(self) -> bool:
        return self.phase not in self.LIVE_PHASES

    @property
    def questions(self) -> tuple[Question, ...]:
        return self.question_set.questions if self.question_set else ()

    @property
    def current_question(self) -> Question | None:
        if 0 <= self.question_index < len(self.questions):
            return self.questions[self.question_index]
        return None

    @property
    def is_last_question(self) -> bool:
        return self.question_index >= len(self.questions) - 1

    def winners(self) -> list[str]:
        """Top scorer(s); empty if nobody scored."""
        best = max(self.players.values(), default=0)
        if best == 0:
            return []
        return [player for player, score in self.players.items() if score == best]

    async def load_questions(self, question_set: QuestionSet) -> bool:
        """Swap in a question set. Only allowed in the lobby so a game can't change mid-way."""
        async with self._buzz_lock:
            if self.phase != "lobby":
                return False
            self.question_set = question_set
            self.question_index = -1
            return True

    def seconds_left(self) -> float:
        if self.answer_deadline is None:
            return 0.0
        return max(0.0, self.answer_deadline - time.monotonic())

    async def join(self, player: str) -> None:
        # a player coming back after a dropped connection keeps their score
        self.players.setdefault(player, 0)
        logger.debug(f"{player} has joined the game!")

    async def add_chat_message(self, player: str, message: str) -> None:
        self.chat_messages.append({"player": player, "message": message})
        self.chat_messages = self.chat_messages[-50:]

    async def buzz(self, player: str) -> bool:
        """Attempt to claim the buzz lock. Returns True if this player is the first-in."""
        async with self._buzz_lock:
            if not self.buzzing_open:
                return False
            if player not in self.players:
                return False
            if player in self.current_lossers:
                return False
            self.current_winner = player
            self.current_answer = None
            self.answer_round = next(_answer_rounds)
            self.answer_deadline = time.monotonic() + ANSWER_SECONDS
            self.phase = "answering"
            return True

    async def submit_answer(self, player: str, answer: str) -> bool:
        """Record the winner's answer for the host to judge. Returns False if it isn't accepted."""
        async with self._buzz_lock:
            if self.phase != "answering" or player != self.current_winner or not answer:
                return False
            self.current_answer = answer
            self.answer_deadline = None
            self.phase = "judging"
            return True

    async def expire_answer(self, answer_round: int) -> bool:
        """Count the winner as wrong if they're still typing in this round. Returns True if it fired."""
        async with self._buzz_lock:
            if self.phase != "answering" or answer_round != self.answer_round:
                return False
            self._lock_out_winner()
            return True

    async def next_question(self) -> None:
        async with self._buzz_lock:
            if self.phase == "game_over":
                return
            if self.phase == "lobby" and not self.questions:
                return
            self._clear_turn()
            self.current_lossers.clear()
            self.last_result = None
            if self.phase in self.LIVE_PHASES:
                # skipped before anyone got it: show the answer before moving on
                self.phase = "reveal"
                return
            self.question_index += 1
            self.phase = "question" if self.current_question else "game_over"

    async def mark_correct(self) -> None:
        async with self._buzz_lock:
            if self.phase != "judging" or self.current_winner is None:
                raise RuntimeError("No answer to judge!")
            self.players[self.current_winner] += 1
            self.last_result = {"player": self.current_winner, "answer": self.current_answer, "correct": True}
            self._clear_turn()
            self.phase = "intermission"

    async def mark_wrong(self) -> None:
        async with self._buzz_lock:
            if self.phase != "judging" or self.current_winner is None:
                raise RuntimeError("No answer to judge!")
            self._lock_out_winner()

    async def reset(self, question_set: QuestionSet | None = None) -> None:
        """Back to the lobby with the same set, or the given (freshly reloaded) one."""
        async with self._buzz_lock:
            self._clear_turn()
            self.phase = "lobby"
            self.question_index = -1
            if question_set is not None:
                self.question_set = question_set
            self.players = {}
            self.current_lossers = []
            self.last_result = None
            self.chat_messages = []

    def _lock_out_winner(self) -> None:
        # current_answer is None when the winner ran out of time
        self.last_result = {"player": self.current_winner, "answer": self.current_answer, "correct": False}
        self.current_lossers.append(self.current_winner)
        self._clear_turn()
        self.phase = "question"

    def _clear_turn(self) -> None:
        self.current_winner = None
        self.current_answer = None
        self.answer_deadline = None
