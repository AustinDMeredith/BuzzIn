from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.game import Game
from app.manager import ConnectionManager

app = FastAPI(title="BuzzIn", description="A live buzzer trivia game for a whole room.")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="app/templates")

game = Game()
manager = ConnectionManager()


@app.get("/")
async def index(request: Request):
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
            # TODO: dispatch on message["type"]: join, buzz, next, correct, wrong, reset
    except WebSocketDisconnect:
        manager.disconnect(websocket)
