# BuzzIn

A live buzzer trivia game for a whole room. A host puts up a question, every player races to hit the buzzer, the first buzz wins, everyone else locks out, and the leaderboard updates on every screen at once, all over WebSockets.
 
**Live:** https://buzzin.services.austinmeredithlabs.com
 
## Features
 
- Join from any phone or laptop with just a name
- Questions appear for every player at the same instant
- First buzz wins, enforced on the server with an `asyncio.Lock` so there's never two winners
- Host controls: next question, mark right/wrong, reopen buzzing, reset game
- Live player count and shared leaderboard
- Load-test script that spins up 25 bot players

## Tech Stack
 
| Layer | Tool |
| --- | --- |
| Backend | Python 3.12, FastAPI (native WebSockets), Uvicorn |
| Frontend | HTMX + WebSocket extension, Jinja2 templates |
| Packaging | uv |
| Deployment | Docker, Traefik (HTTPS via Let's Encrypt), homelab |
| CI | GitHub Actions → GitHub Container Registry |
 
## Project Structure
 
```
buzzin/
├── app/
│   ├── main.py          # FastAPI app, routes, WebSocket endpoint
│   ├── game.py          # Game state, buzz lock, scoring
│   ├── manager.py       # Connection tracking and broadcast
│   └── templates/       # Jinja2 pages and HTML fragments
├── static/              # CSS and the small bit of JS (spacebar buzz)
├── loadtest/
│   └── bots.py          # 25-bot WebSocket load test
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```
 
## Running Locally
 
Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).
 
```bash
git clone https://github.com/<your-username>/buzzin.git
cd buzzin
uv sync
uv run uvicorn app.main:app --reload
```
 
Open http://localhost:8000 to play, and http://localhost:8000/host for host controls.
 
## Load Test
 
With the server running, launch the bots:
 
```bash
uv run python loadtest/bots.py --url ws://localhost:8000/ws --bots 25
```
 
Each bot joins, waits for questions, and buzzes at a random delay. The script reports connections held and confirms each question had exactly one winner. Point `--url` at `wss://buzzin.services.austinmeredithlabs.com/ws` to test the deployed server.
 
## Deployment
 
BuzzIn runs as a single container behind Traefik. **Use one Uvicorn worker** since game state lives in memory, so multiple workers would split players into separate games.
 
```yaml
services:
  buzzin:
    image: ghcr.io/<your-username>/buzzin:latest
    container_name: buzzin
    restart: unless-stopped
    labels:
      - traefik.enable=true
      - traefik.http.routers.buzzin.rule=Host(`buzzin.services.austinmeredithlabs.com`)
      - traefik.http.routers.buzzin.tls.certresolver=letsencrypt
      - traefik.http.services.buzzin.loadbalancer.server.port=8000
    networks:
      - traefik
 
networks:
  traefik:
    external: true
```
 
```bash
docker compose pull && docker compose up -d
```
 
Traefik passes WebSocket upgrades through automatically. Uvicorn's default 20-second ping keeps sockets alive through Cloudflare's idle timeout.
 
## Message Protocol
 
All messages are JSON with a `type` field.
 
| Direction | Type | Purpose |
| --- | --- | --- |
| Client → Server | `join` | Join with a display name |
| Client → Server | `buzz` | Attempt to buzz in |
| Host → Server | `next`, `correct`, `wrong`, `reset` | Host controls |
| Server → Client | HTML fragments | HTMX swaps question, buzzer, and leaderboard by element ID |
 
## Author
 
Austin Meredith, Abilene Christian University
