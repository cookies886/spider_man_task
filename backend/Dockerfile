FROM python:3.12-slim

WORKDIR /app

# Minimal runtime deps: gcc/make for building wheels, git for slice 3 git_sync,
# xz-utils for tar -xJ. Heavy Python-source-build deps (libssl-dev, etc.) are
# included only when PYVER_BUILD=1 is set at build time.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    xz-utils \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY app ./app
RUN pip install --no-cache-dir -e ".[dev]"

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
