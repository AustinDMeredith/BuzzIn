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
    try:
        while True:
            message = await websocket.receive_json()
            logger.debug(message)
            # TODO: dispatch on message["type"]: join, buzz, next, correct, wrong, reset
            match message['type']:
                case 'join':
                    # player name sent in message['player']
                    await game.join(message['player'])
                case 'buzz':
                    logger.debug("received buzz from client")

    except WebSocketDisconnect:
        manager.disconnect(websocket)
