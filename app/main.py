from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import logging

from app.game import Game
from app.manager import ConnectionManager

# init app
app = FastAPI(title="BuzzIn", description="A live buzzer trivia game for a whole room.")

# init logger for module
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# grab html to return to client
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="app/templates")

#start a new game and ConnectionManager
game = Game()
manager = ConnectionManager()


def render_screen(name: str, **context) -> str:
    return templates.get_template(f"partials/{name}").render(**context)


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
            message = await websocket.receive_json()
            # TODO: dispatch on message["type"]: join, buzz, next, correct, wrong, reset, chat
            match message['type']:
                case 'join':
                    # player name sent in message['player']
                    player_name = str(message['player'])
                    await game.join(player_name)
                    manager.register(player_name, websocket)
                    await manager.broadcast(render_screen(
                        "lobby.html", players=game.players, chat_messages=game.chat_messages
                    ))
                case 'buzz':
                    logger.debug("received buzz from client")
                    if player_name is not None:
                        is_winner = await game.buzz(player_name)
                        if is_winner:
                            logger.debug(f"{player_name} buzzed in!")
                        

                case 'chat':
                    if player_name is not None:
                        await game.add_chat_message(player_name, str(message['message']))
                        await manager.broadcast(render_screen(
                            "lobby.html", players=game.players, chat_messages=game.chat_messages
                        ))

    except WebSocketDisconnect:
        if player_name is not None:
            manager.disconnect(player_name)
