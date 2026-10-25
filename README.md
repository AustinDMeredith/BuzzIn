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
│   ├── questions.py     # Loading and validating question sets
│   └── templates/       # Jinja2 pages and HTML fragments
├── questions/           # Question sets, one .json file each
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
 
## Question Sets

Questions live in the `questions/` folder. Each `.json` file is one set, and the host picks which set to play from a dropdown on `/host` before starting the game.

A set is a list of question/answer pairs, asked in file order:

```json
[
  {"question": "What is the capital of France?", "answer": "Paris"},
  {"question": "How many legs does a spider have?", "answer": "8"}
]
```

- The file name becomes the set's title: `world-capitals.json` shows up as "World Capitals".
- New or edited files are picked up when the host loads a set, resets the game, or reloads `/host` — no restart needed.
- A broken file is listed (disabled) on the host page with an error saying which entry is wrong; the other sets still work.
- Set `QUESTIONS_DIR` to read sets from a different folder. In Docker, uncomment the `volumes` line in `docker-compose.yml` to edit sets on the server without rebuilding.

## Tests

```bash
uv run pytest                    # everything
uv run pytest tests/unit         # game, connection manager, templates, JS/template contracts
uv run pytest tests/integration  # HTTP routes + real WebSocket clients against a live uvicorn server
```

The integration workflow runs both suites on every pull request to `main`.

## Load Test
 
With the server running, launch the bots:
 
```bash
uv run python loadtest/bots.py --url ws://localhost:8000/ws --bots 25
```
 
By default the script also runs a bot host that starts the game, marks every answer correct, and moves on until game over. Each bot joins, buzzes at a random delay when a question opens, and answers if it wins. At the end the script reports connections held, the winner of every buzz round (each must have exactly one), and how fast a winning buzz reaches the screen. It exits non-zero on any failure.

| Flag | Default | Purpose |
| --- | --- | --- |
| `--bots` | 25 | Number of bot players |
| `--no-host` | off | Skip the bot host and run the game yourself from `/host`; Ctrl+C prints the report |
| `--min-delay`, `--max-delay` | 0.05, 1.0 | Range of each bot's random buzz delay, in seconds |
| `--set` | server default | Question set id to load first, e.g. `general-knowledge` |

The bot host takes over host controls and resets the game if it isn't in the lobby, so don't run it during a real game. Point `--url` at `wss://buzzin.services.austinmeredithlabs.com/ws` to test the deployed server.
 
## Deployment
 
BuzzIn runs as a single container behind Traefik. **Use one Uvicorn worker** since game state lives in memory, so multiple workers would split players into separate games.
 
```yaml
name: BuzzIn
services:
  buzzin:
    image: ghcr.io/austindmeredith/buzzin:latest
    container_name: buzzin
    restart: unless-stopped
    volumes:
      - ./<path to questions dir>:/app/questions:ro
    labels:
      - <proxy settings here>
    networks:
      - <your docker network>
 
networks:
  <your docker network>:
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
| Client → Server | `answer` | First player in submits their answer (15 seconds, or it counts as wrong) |
| Client → Server | `chat` | Chat message (lobby and between questions only) |
| Host → Server | `host_join` | Claim the host controls |
| Host → Server | `choose_set` | Pick a question set (lobby only) |
| Host → Server | `next`, `correct`, `wrong`, `reset` | Host controls (`next` starts the game from the lobby) |
| Server → Client | HTML fragments | HTMX swaps question, buzzer, and leaderboard by element ID |
 
## Author
 
Austin Meredith, Abilene Christian University
