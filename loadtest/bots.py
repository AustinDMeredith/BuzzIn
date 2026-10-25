"""Load test: bot players (and, by default, a bot host) play a whole game over WebSockets.

The server only sends HTML fragments, so the bots read the game state from what's on screen.
"""
import argparse
import asyncio
import json
import random
import re
import statistics
import sys
import time
from dataclasses import dataclass, field
from html import unescape

import websockets

HOST_NAME = "LoadTest Host"
JOIN_TIMEOUT = 30.0  # for every bot to finish joining
IDLE_TIMEOUT = 30.0  # the bot host gives up if nothing happens for this long
DRAIN_TIMEOUT = 5.0  # how long bots get to see game over after the host does

QUESTION = re.compile(r"Question (\d+) of (\d+)")
BUZZ_BUTTON = re.compile(r'<button id="buzz-button"[^>]*>')
SOMEONE_ELSE_ANSWERING = re.compile(r"<h2>(.+?) is answering…</h2>")
YOU_WON = "You buzzed in first!"
PLAYER_COUNT = re.compile(r"Leaderboard \((\d+) players\)")
ERROR = re.compile(r'<p class="error">(.*?)</p>', re.S)


@dataclass
class Round:
    """One buzz round: a question opens (or reopens after a wrong answer) and someone buzzes first."""
    claims: list[str] = field(default_factory=list)  # bots told "You buzzed in first!"
    seen: set[str] = field(default_factory=set)  # the winner, as every bot saw it

    @property
    def ok(self) -> bool:
        return len(self.seen) == 1 and len(self.claims) <= 1 and set(self.claims) <= self.seen


@dataclass
class Stats:
    bots: int
    hosted: bool = True
    connected: int = 0
    failed: dict[str, str] = field(default_factory=dict)
    dropped: list[str] = field(default_factory=list)
    question_count: int = 0
    rounds: dict[tuple[int, int], Round] = field(default_factory=dict)
    latencies: list[float] = field(default_factory=list)  # winning buzz -> "You buzzed in first!"
    server_players: int = 0
    game_over: bool = False
    host_error: str | None = None
    all_joined: asyncio.Event = field(default_factory=asyncio.Event)

    @property
    def held(self) -> int:
        return self.connected - len(self.dropped)

    def settle(self) -> None:
        if self.connected + len(self.failed) >= self.bots:
            self.all_joined.set()

    def failures(self) -> list[str]:
        problems = []
        if self.connected < self.bots:
            problems.append(f"only {self.connected}/{self.bots} bots connected")
        if self.dropped:
            problems.append(f"{len(self.dropped)} bots dropped mid-game")
        if not self.rounds:
            problems.append("no buzz rounds were played")
        for (question, number), round_ in sorted(self.rounds.items()):
            if not round_.ok:
                problems.append(f"question {question} round {number} had winners {sorted(round_.seen | set(round_.claims))}")
        if self.hosted:
            if self.host_error:
                problems.append(f"bot host: {self.host_error}")
            elif not self.game_over:
                problems.append("the game never finished")
            played = {question for question, _ in self.rounds}
            if self.question_count and played != set(range(1, self.question_count + 1)):
                problems.append(f"questions with no winner: {sorted(set(range(1, self.question_count + 1)) - played)}")
            if self.server_players < self.connected:
                problems.append(f"host saw {self.server_players} players but {self.connected} bots connected")
        return problems


async def send(ws, type: str, **fields) -> None:
    await ws.send(json.dumps({"type": type, **fields}))


def error_text(html: str) -> str:
    match = ERROR.search(html)
    return unescape(re.sub(r"<[^>]+>", "", match[1])).strip() if match else "unknown error"


# ---------------- players ----------------

async def run_bot(index: int, url: str, stats: Stats, delays: tuple[float, float]) -> None:
    name = f"bot-{index:02d}"
    try:
        ws = await websockets.connect(url)
    except Exception as exc:
        stats.failed[name] = repr(exc)
        stats.settle()
        return
    async with ws:
        try:
            # retry once with a suffix in case a previous run's bot still holds the name
            for attempt in (name, f"{name}-{random.randrange(1000):03d}"):
                await send(ws, "join", player=attempt)
                html = await asyncio.wait_for(ws.recv(), JOIN_TIMEOUT)
                if 'class="error"' not in html:
                    name = attempt
                    stats.connected += 1
                    break
            else:
                stats.failed[name] = f"join rejected: {error_text(html)}"
                return
        except Exception as exc:
            stats.failed[name] = repr(exc)
            return
        finally:
            stats.settle()

        buzz_timers: set[asyncio.Task] = set()
        buzzed_at: float | None = None
        rounds_seen: dict[int, int] = {}
        question = 0
        played = False  # joining a finished game shouldn't end the bot before it plays

        async def buzz_later() -> None:
            nonlocal buzzed_at
            await asyncio.sleep(random.uniform(*delays))
            buzzed_at = time.perf_counter()
            await send(ws, "buzz")

        try:
            while True:
                if "Game over" in html and played:
                    return
                if "Enter your username" in html:  # the host reset the game, so join the next one
                    await send(ws, "join", player=name)
                if match := QUESTION.search(html):
                    question, stats.question_count = int(match[1]), int(match[2])

                winner = name if YOU_WON in html else None
                if match := SOMEONE_ELSE_ANSWERING.search(html):
                    winner = unescape(match[1])
                if winner:
                    played = True
                    rounds_seen[question] = rounds_seen.get(question, 0) + 1
                    round_ = stats.rounds.setdefault((question, rounds_seen[question]), Round())
                    round_.seen.add(winner)
                    if winner == name:
                        round_.claims.append(name)
                        if buzzed_at is not None:
                            stats.latencies.append(time.perf_counter() - buzzed_at)
                        await send(ws, "answer", answer="bot answer")
                # each fragment with an open buzzer is a fresh opening (chat is closed mid-question)
                elif (button := BUZZ_BUTTON.search(html)) and "disabled" not in button[0]:
                    played = True
                    task = asyncio.create_task(buzz_later())
                    buzz_timers.add(task)
                    task.add_done_callback(buzz_timers.discard)

                html = await ws.recv()
        except websockets.ConnectionClosed:
            stats.dropped.append(name)
        finally:
            for task in buzz_timers:
                task.cancel()


# ---------------- host ----------------

async def host_setup(url: str, set_id: str | None):
    """Claim host controls and get the game back to a lobby before any bots join."""
    ws = await websockets.connect(url)
    await send(ws, "host_join", host=HOST_NAME)
    html = await asyncio.wait_for(ws.recv(), IDLE_TIMEOUT)
    if "Waiting to start." not in html:
        await send(ws, "reset")
        html = await asyncio.wait_for(ws.recv(), IDLE_TIMEOUT)
    if set_id:
        await send(ws, "choose_set", question_set=set_id)
        html = await asyncio.wait_for(ws.recv(), IDLE_TIMEOUT)
        if not re.search(rf'<option value="{re.escape(set_id)}"[^>]*selected', html):
            await ws.close()
            raise RuntimeError(f"couldn't load question set {set_id!r}: {error_text(html)}")
    return ws


def note_players(html: str, stats: Stats) -> None:
    if match := PLAYER_COUNT.search(html):
        stats.server_players = int(match[1])


async def drive_game(ws, stats: Stats) -> None:
    """Start once every bot has joined, then mark every answer correct and move on until game over."""
    deadline = time.monotonic() + JOIN_TIMEOUT
    while not (stats.all_joined.is_set() and stats.server_players >= stats.connected):
        if time.monotonic() > deadline:
            raise RuntimeError("bots never finished joining")
        try:
            note_players(await asyncio.wait_for(ws.recv(), 0.25), stats)
        except TimeoutError:
            pass
    if not stats.connected:
        raise RuntimeError("no bots connected")

    await send(ws, "next")
    # a stray chat message re-sends the same screen, so only act once per question and step
    acted: set[tuple[str, int]] = set()
    while True:
        try:
            html = await asyncio.wait_for(ws.recv(), IDLE_TIMEOUT)
        except TimeoutError:
            raise RuntimeError(f"game stalled for {IDLE_TIMEOUT:.0f}s") from None
        note_players(html, stats)
        if "Game over" in html:
            stats.game_over = True
            return
        match = QUESTION.search(html)
        question = int(match[1]) if match else 0
        if 'answered: "' in html and ("correct", question) not in acted:
            acted.add(("correct", question))
            await send(ws, "correct")
        elif "got it! (" in html and ("next", question) not in acted:
            acted.add(("next", question))
            await send(ws, "next")


# ---------------- run + report ----------------

async def run(
    url: str,
    bots: int,
    *,
    host: bool = True,
    delays: tuple[float, float] = (0.05, 1.0),
    set_id: str | None = None,
    stats: Stats | None = None,
) -> Stats:
    stats = stats or Stats(bots, hosted=host)
    host_ws = None
    if host:
        try:
            host_ws = await host_setup(url, set_id)
        except Exception as exc:
            stats.host_error = str(exc) if isinstance(exc, RuntimeError) else repr(exc)
            return stats

    tasks = [asyncio.create_task(run_bot(i, url, stats, delays)) for i in range(1, bots + 1)]
    if host_ws is None:
        await asyncio.gather(*tasks)
        return stats

    try:
        await drive_game(host_ws, stats)
    except Exception as exc:
        stats.host_error = str(exc) if isinstance(exc, RuntimeError) else repr(exc)
    finally:
        await host_ws.close()
    _, pending = await asyncio.wait(tasks, timeout=DRAIN_TIMEOUT)
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)
    return stats


def report(stats: Stats) -> bool:
    print(
        f"\nConnections: {stats.connected}/{stats.bots} connected, {stats.held} held to the end, "
        f"{len(stats.dropped)} dropped, {len(stats.failed)} failed"
    )
    for name, reason in sorted(stats.failed.items()):
        print(f"  {name}: {reason}")

    print("\nBuzz rounds:")
    for (question, number), round_ in sorted(stats.rounds.items()):
        winners = ", ".join(sorted(round_.seen | set(round_.claims))) or "nobody"
        print(f"  Q{question} round {number}: {winners} {'✅' if round_.ok else '❌'}")

    if stats.latencies:
        ms = sorted(seconds * 1000 for seconds in stats.latencies)
        print(f"\nWinning buzz → screen update: min {ms[0]:.1f}ms, median {statistics.median(ms):.1f}ms, max {ms[-1]:.1f}ms")

    failures = stats.failures()
    print("\nPASS" if not failures else "\nFAIL")
    for problem in failures:
        print(f"  - {problem}")
    return not failures


def main() -> None:
    parser = argparse.ArgumentParser(description="Spin up bot players to load-test BuzzIn.")
    parser.add_argument("--url", required=True, help="WebSocket URL, e.g. ws://localhost:8000/ws")
    parser.add_argument("--bots", type=int, default=25, help="Number of bot players to connect")
    parser.add_argument("--no-host", action="store_true", help="Don't run a bot host; drive the game yourself from /host")
    parser.add_argument("--min-delay", type=float, default=0.05, help="Shortest buzz delay in seconds")
    parser.add_argument("--max-delay", type=float, default=1.0, help="Longest buzz delay in seconds")
    parser.add_argument("--set", dest="set_id", help="Question set id to load first, e.g. general-knowledge")
    args = parser.parse_args()
    if args.bots < 1:
        parser.error("--bots must be at least 1")
    if not 0 <= args.min_delay <= args.max_delay:
        parser.error("need 0 <= --min-delay <= --max-delay")

    stats = Stats(args.bots, hosted=not args.no_host)
    if stats.hosted:
        print("Bot host is taking over host controls (and resetting the game if it isn't in the lobby).")
    else:
        print("Waiting for you to run the game from /host. Ctrl+C to stop.")
    print(f"Connecting {args.bots} bots to {args.url}…")
    try:
        asyncio.run(run(
            args.url, args.bots, host=stats.hosted, delays=(args.min_delay, args.max_delay),
            set_id=args.set_id, stats=stats,
        ))
    except KeyboardInterrupt:
        print("\nInterrupted.")
    sys.exit(0 if report(stats) else 1)


if __name__ == "__main__":
    main()
