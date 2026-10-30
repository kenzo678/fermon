FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app

FROM base AS dev
COPY pyproject.toml uv.lock ./
RUN \
    uv sync --frozen --no-install-project
COPY . .
RUN uv sync --frozen
CMD ["uvicorn", "fermon.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS prod
COPY pyproject.toml uv.lock ./
RUN \
    uv sync --frozen --no-dev --no-install-project
COPY . .
RUN uv sync --frozen --no-dev
RUN useradd --system --no-create-home app
USER app
CMD ["uvicorn", "fermon.main:app", "--host", "0.0.0.0", "--port", "8000"]
