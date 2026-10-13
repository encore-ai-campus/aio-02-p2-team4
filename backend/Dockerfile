# Backend production image (FastAPI). Used only for hosted deploys;
# local development keeps using `uv run uvicorn main:app ...`.
FROM python:3.12-slim AS base
WORKDIR /app
RUN adduser --system --group --home /home/app app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-cache
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN mkdir -p "$PLAYWRIGHT_BROWSERS_PATH" \
    && uv run --no-sync playwright install --with-deps --only-shell chromium \
    && chmod -R a+rX "$PLAYWRIGHT_BROWSERS_PATH"
COPY --chown=app:app . ./
USER app
EXPOSE 8010
CMD ["sh", "-c", ".venv/bin/uvicorn main:app --host 0.0.0.0 --port ${PORT:-8010}"]
