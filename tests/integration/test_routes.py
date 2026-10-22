import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.helpers import screen_of


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


def test_index_serves_player_page(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    html = response.text
    assert screen_of(html) == "join"
    assert 'ws-connect="/ws"' in html
    assert "htmx.org@" in html and "htmx-ext-ws@" in html
    assert "/static/js/buzz.js" in html
    assert "/static/js/countdown.js" in html


def test_host_serves_host_page(client):
    response = client.get("/host")
    assert response.status_code == 200
    html = response.text
    assert screen_of(html) == "host_start"
    assert 'ws-connect="/ws"' in html
    assert "/static/js/countdown.js" in html


@pytest.mark.parametrize("path, content_type", [
    ("/static/js/buzz.js", "javascript"),
    ("/static/js/countdown.js", "javascript"),
    ("/static/css/style.css", "text/css"),
])
def test_static_files_served(client, path, content_type):
    response = client.get(path)
    assert response.status_code == 200
    assert content_type in response.headers["content-type"]


@pytest.mark.parametrize("path", ["/nope", "/static/js/nope.js", "/static/../app/main.py"])
def test_unknown_paths_404(client, path):
    assert client.get(path).status_code == 404


def test_websocket_accepts_connection(client):
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"type": "join", "player": "alice"})
        assert screen_of(ws.receive_text()) == "lobby"
