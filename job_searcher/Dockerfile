# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# curl is only for the container HEALTHCHECK and manual debugging on the box.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

# Dependencies first - this layer is cached until requirements.txt changes.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Application code. frontend/dist is a pre-built static bundle (built locally
# with `npm run build` and committed) - the box never runs Node/npm, which
# matters on a 1 GB t3.micro. The web app is multi-tenant and reads each
# visitor's own uploaded profile - the personal data/profile.md (CLI/Discord
# bot only) is deliberately not baked into this image.
COPY src ./src
COPY backend ./backend
COPY frontend/dist ./frontend/dist

# Run unprivileged.
RUN useradd --create-home --uid 10001 appuser \
 && mkdir -p /app/backend/data \
 && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
  CMD curl -fsS http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
