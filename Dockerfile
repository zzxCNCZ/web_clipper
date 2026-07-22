# syntax=docker/dockerfile:1.7

FROM python:3.13-slim

LABEL maintainer="Banksy"
LABEL description="Web Clipper FastAPI service"

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:0.11.29 /uv /uvx /bin/

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

COPY app ./app
COPY run.py main.py web_clipper.py ./

RUN mkdir -p /app/uploads

EXPOSE 65330

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:65330/health', timeout=3)"]

CMD ["uvicorn", "run:app", "--host", "0.0.0.0", "--port", "65330"]
