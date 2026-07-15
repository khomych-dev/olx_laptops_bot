# ── Stage 1: install dependencies ────────────────────────────────────────────
FROM python:3.12-slim AS builder

# Install uv (the package manager the project uses)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy only the dependency manifest files first so Docker can cache this layer
COPY pyproject.toml uv.lock ./

# Install production dependencies only into /app/.venv
RUN uv sync --frozen --no-dev

# ── Stage 2: final lean image ─────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Copy the pre-built virtual environment from the builder stage
COPY --from=builder /app/.venv /app/.venv

# Copy the application source code
COPY main.py ./
COPY app/ ./app/

# Make the venv's binaries take priority so `python` resolves to the venv
ENV PATH="/app/.venv/bin:$PATH"

# The SQLite database is written to /app/data inside the container.
# Mount a host volume here to persist the database across container restarts.
VOLUME ["/app/data"]

# Tell the app to write the DB inside the mounted data directory.
# app/database.py reads DB_NAME from an env variable when it is set.
ENV DB_PATH=/app/data/bot_data.sqlite3

CMD ["python", "main.py"]
