# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# curl is only for the container HEALTHCHECK and manual debugging on the box.
# pandas / numpy / pydantic-core all ship manylinux wheels for 3.12, so no
# compiler is needed and the image stays lean.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

# Dependencies first — this layer is cached until requirements.txt changes.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Application code (app/static/index.html is the whole dashboard — inline CSS/JS).
COPY app ./app

# Run unprivileged.
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
  CMD curl -fsS http://localhost:8000/health || exit 1

# One worker on purpose: /analyze is CPU- and RAM-heavy and the free-tier
# t3.micro only has 1 GB. Scale workers up only on a bigger box.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
