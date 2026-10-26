FROM python:3.12-alpine3.22 AS base
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

FROM base AS builder
COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /bin/uv
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 uv sync --frozen --no-dev --no-install-project --no-managed-python --python /usr/local/bin/python

FROM base AS runtime
RUN addgroup -S appuser && adduser -S -G appuser appuser
COPY --from=builder /app/.venv ./.venv
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
USER appuser
EXPOSE 5000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5000"]
