FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

COPY --from=ghcr.io/astral-sh/uv:0.11.13 /uv /usr/local/bin/uv

WORKDIR /app

# Build context is the repository root (see infra/docker-compose.yml).
COPY pyproject.toml uv.lock ./
COPY packages packages
COPY services/api services/api
RUN uv sync --frozen --no-dev --no-editable --package opspilot-api

RUN useradd --system --uid 10001 app
USER app

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000

CMD ["uvicorn", "opspilot_api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
