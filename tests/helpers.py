import asyncio
import re
import time

# a phrase that only appears on each screen, used to tell them apart
SCREENS = {
    "join": "Enter your username",
    "lobby": "Waiting for players",
    "game": "Playing as",
    "host_start": "Enter your host name",
    "host": "Hosting as",
}


def screen_of(html: str) -> str:
    matches = [name for name, marker in SCREENS.items() if marker in html]
    assert len(matches) == 1, f"expected exactly one screen, found {matches}:\n{html}"
    return matches[0]


def text(html: str) -> str:
    """Strip tags and collapse whitespace so assertions can match visible text."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def buzz_enabled(html: str) -> bool:
    button = re.search(r'<button id="buzz-button"[^>]*>', html)
    assert button, f"no buzz button in:\n{html}"
    return "disabled" not in button.group(0)


def leaderboard(html: str) -> list[str]:
    board = re.search(r'<ol id="leaderboard">(.*?)</ol>', html, re.S)
    assert board, f"no leaderboard in:\n{html}"
    return [text(item) for item in re.findall(r"<li>(.*?)</li>", board.group(1), re.S)]


async def wait_until(condition, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("condition never became true")
        await asyncio.sleep(0.01)


TEST_QUESTIONS = [
    {"question": "First test question?", "answer": "ANSWER-ONE"},
    {"question": "Second test question?", "answer": "ANSWER-TWO"},
    {"question": "Third test question?", "answer": "ANSWER-THREE"},
]


def make_set(set_id: str = "test-set", questions: list[dict] | None = None):
    from app.questions import Question, QuestionSet, display_name
    questions = TEST_QUESTIONS if questions is None else questions
    return QuestionSet(set_id, display_name(set_id), tuple(Question(**q) for q in questions))


TEST_SET = make_set()
