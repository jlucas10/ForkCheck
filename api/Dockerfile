FROM python:3.13-slim

# uv: the same tool we use locally to install dependencies from uv.lock.
COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /usr/local/bin/uv

WORKDIR /srv

# Install dependencies first, in their own layer. Docker caches layers, so
# this only reruns when pyproject.toml or uv.lock change, not on every code edit.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Then copy the application code.
COPY app ./app

# Run as an unprivileged user, not root.
RUN useradd --system --no-create-home appuser
USER appuser

ENV PATH="/srv/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

# Railway and Render tell the container which port to listen on via $PORT.
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
