# Backend image: API, Celery worker and beat all run from this one image (different commands).
# Build context: repo root. `docker compose --profile app build` does this for you.

FROM python:3.13-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    HF_HOME=/opt/hf \
    PATH=/app/backend/.venv/bin:$PATH

# libgomp: OpenMP runtime for LightGBM / PyTorch on slim images.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 \
 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.13.8 /uv /bin/uv
WORKDIR /app/backend

# Dependencies first (cached layer): exactly the versions in uv.lock, no dev tools.
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-install-project

# Bake the two models into the image, so containers start offline and never download at runtime.
RUN python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; \
SentenceTransformer('BAAI/bge-small-en-v1.5'); CrossEncoder('cross-encoder/ms-marco-MiniLM-L6-v2')"
# From here on, never touch the network for models (no update checks, no surprise downloads).
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1

COPY backend/ ./
COPY data/taxonomy /app/data/taxonomy
COPY data/synthetic /app/data/synthetic
COPY eval /app/eval

# Run as an unprivileged user; it may write only uploads, eval reports and the beat schedule.
RUN useradd --create-home --uid 10001 app \
 && mkdir -p /app/data/private/uploads \
 && chown -R app:app /app/data/private /app/eval/reports
USER app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
