from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import asyncio
import logging
import math
import os

from app.game import Game
from app.manager import ConnectionManager
from app.questions import QuestionSet, scan_sets

# init app
app = FastAPI(title="BuzzIn", description="A live buzzer trivia game for a whole room.")

# init logger for module
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# grab html to return to client
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# question sets are *.json files in this folder; the host picks one in the lobby
QUESTIONS_DIR = os.environ.get("QUESTIONS_DIR", "questions")
question_sets: list[QuestionSet] = scan_sets(QUESTIONS_DIR)
question_error: str | None = None


def first_valid_set() -> QuestionSet | None:
    return next((s for s in question_sets if s.error is None), None)


# start a new game (with the first good set loaded) and ConnectionManager
game = Game(first_valid_set())
manager = ConnectionManager()

MAX_NAME_LENGTH = 24
MAX_CHAT_LENGTH = 200
MAX_ANSWER_LENGTH = 100

# helper to render partials
def render_screen(name: str, **context) -> str:
    return templates.get_template(f"partials/{name}").render(**context)


# trim user-supplied text and cap its length
def clean_text(value: object, max_length: int) -> str:
    if value is None:
        return ""
    return str(value).strip()[:max_length]


# receive one frame, returning None for anything that isn't a JSON object with a string type
async def read_message(websocket: WebSocket) -> dict | None:
    try:
        message = await websocket.receive_json()
    except (ValueError, KeyError, TypeError):  # bad JSON or a binary frame
        return None
    if not isinstance(message, dict) or not isinstance(message.get('type'), str):
        return None
    return message


# everything the game and host screens need to render the current state
def game_context(**extra) -> dict:
    return dict(
        phase=game.phase,
        players=game.players,
        current_winner=game.current_winner,
        current_answer=game.current_answer,
        current_lossers=game.current_lossers,
        last_result=game.last_result,
        seconds_left=math.ceil(game.seconds_left()),
        chat_messages=game.chat_messages,
        chat_open=game.chat_open,
        question_set=game.question_set,
        question=game.current_question,
        question_number=game.question_index + 1,
        question_count=len(game.questions),
        is_last_question=game.is_last_question,
        winners=game.winners(),
        **extra,
    )


# push the current game state to the host's control panel
async def update_host() -> None:
    await manager.send_host(render_screen("host_controls.html", **game_context(
        host=game.host, sets=question_sets, question_error=question_error,
    )))


# re-read the folder so newly added or edited sets show up without a restart
async def refresh_sets() -> None:
    global question_sets
    question_sets = scan_sets(QUESTIONS_DIR)
    if game.question_set is None and (default := first_valid_set()):
        await game.load_questions(default)


# load the host's pick fresh from disk; the id is matched against the scan, never used as a path
async def choose_set(set_id: object) -> bool:
    """Returns True if the set was loaded."""
    global question_error
    await refresh_sets()
    chosen = next((s for s in question_sets if s.id == set_id), None)
    if chosen is None:
        question_error = "That question set wasn't found."
    elif chosen.error:
        question_error = chosen.error
    elif await game.load_questions(chosen):
        question_error = None
        return True
    return False


# the current set as it is on disk now, or the copy already loaded if the file broke or vanished
async def reload_current_set() -> QuestionSet | None:
    global question_error
    await refresh_sets()
    current = game.question_set
    if current is None:
        return None
    fresh = next((s for s in question_sets if s.id == current.id), None)
    if fresh is None:
        question_error = f"{current.name} was removed from the folder; keeping the copy already loaded."
        return current
    if fresh.error:
        question_error = f"Couldn't reload {current.name}, keeping the copy already loaded: {fresh.error}"
        return current
    question_error = None
    return fresh


# push the lobby before the game starts, then each player's own game screen
# pass `only` to update just one player, e.g. a late joiner, without re-rendering anyone mid-answer
async def update_players(only: str | None = None) -> None:
    if not game.started:
        html = render_screen(
            "lobby.html", players=game.players, chat_messages=game.chat_messages, question_set=game.question_set
        )
        if only:
            await manager.send_to(only, html)
        else:
            await manager.broadcast(html)
        return
    for player in [only] if only else list(manager.active_connections):
        await manager.send_to(player, render_screen("game.html", **game_context(player=player)))


# keep references so pending timers aren't garbage collected
answer_timers: set[asyncio.Task] = set()


# counts the winner as wrong if they haven't answered in time
async def answer_timeout(answer_round: int) -> None:
    await asyncio.sleep(game.seconds_left())
    if await game.expire_answer(answer_round):
        logger.debug("answer timed out")
        await update_players()
        await update_host()


def start_answer_timer() -> None:
    task = asyncio.create_task(answer_timeout(game.answer_round))
    answer_timers.add(task)
    task.add_done_callback(answer_timers.discard)


# --------------ROUTES--------------
@app.get("/")
async def index(request: Request):
    logger.debug(request)
    return templates.TemplateResponse(request, "index.html")


@app.get("/host")
async def host(request: Request):
    return templates.TemplateResponse(request, "host.html")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    player_name: str | None = None
    try:
        while True:
            message = await read_message(websocket)
            if message is None:
                continue
            # re-checked every message: a reset or a new host can take these away
            is_host = manager.host is websocket
            is_player = player_name is not None and manager.is_registered(player_name, websocket)
            match message['type']:
                case 'join' if not is_player:
                    name = clean_text(message.get('player'), MAX_NAME_LENGTH)
                    if not name:
                        await websocket.send_text(render_screen("join.html", error="Enter a name to join."))
                        continue
                    if name in manager.active_connections:
                        await websocket.send_text(render_screen("join.html", error="That name is already taken."))
                        continue
                    player_name = name
                    await game.join(player_name)
                    manager.register(player_name, websocket)
                    # mid-question, only the joiner needs a screen; others' screens don't show the roster
                    await update_players(only=None if game.chat_open else player_name)
                    await update_host()

                case 'host_join':
                    game.host = clean_text(message.get('host'), MAX_NAME_LENGTH) or "Host"
                    manager.register_host(websocket)
                    await refresh_sets()
                    await update_host()

                case 'buzz' if is_player:
                    is_winner = await game.buzz(str(player_name))
                    if is_winner:
                        logger.debug(f"{player_name} buzzed in!")
                        start_answer_timer()
                        await update_players()
                        await update_host()

                case 'answer' if is_player:
                    answer = clean_text(message.get('answer'), MAX_ANSWER_LENGTH)
                    if await game.submit_answer(str(player_name), answer):
                        await update_players()
                        await update_host()

                # chat is hidden while a question is up, so ignore it then too
                case 'chat' if game.chat_open:
                    sender = game.host if is_host else player_name if is_player else None
                    text = clean_text(message.get('message'), MAX_CHAT_LENGTH)
                    if sender is not None and text:
                        await game.add_chat_message(sender, text)
                        await update_players()
                        await update_host()

                # host controls, ignored from anyone but the host
                case 'choose_set' if is_host and game.phase == "lobby":
                    if await choose_set(message.get('question_set')):
                        await update_players()
                    await update_host()

                case 'next' if is_host:
                    await game.next_question()
                    await update_players()
                    await update_host()

                case 'correct' if is_host:
                    try:
                        await game.mark_correct()
                    except RuntimeError:
                        logger.warning("host marked correct with no current winner")
                    await update_players()
                    await update_host()

                case 'wrong' if is_host:
                    try:
                        await game.mark_wrong()
                    except RuntimeError:
                        logger.warning("host marked wrong with no current winner")
                    await update_players()
                    await update_host()

                case 'reset' if is_host:
                    await game.reset(await reload_current_set())
                    # send everyone back to the join screen
                    await manager.broadcast(render_screen("join.html"))
                    manager.active_connections.clear()
                    await update_host()

    except WebSocketDisconnect:
        pass
    finally:
        # always clean up, even if the handler crashed, so broadcasts never hit a dead socket
        manager.disconnect_host(websocket)
        if player_name is not None:
            manager.disconnect(player_name, websocket)
