FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY app ./app
COPY static ./static
COPY questions ./questions

RUN useradd --no-create-home --shell /usr/sbin/nologin appuser
USER appuser

ENV PATH="/app/.venv/bin:$PATH"

# Single worker: game state lives in memory, so multiple workers would split
# players into separate games.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
