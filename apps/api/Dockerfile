FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install the backend package from the repo root (pyproject lives there).
COPY pyproject.toml README.md LICENSE ./
COPY apps/api/src ./apps/api/src
COPY migrations ./migrations
COPY alembic.ini ./
COPY policies ./policies
COPY agents ./agents

RUN pip install --no-cache-dir .

# Non-root runtime user.
RUN useradd --create-home --shell /usr/sbin/nologin zuzu
USER zuzu

EXPOSE 8000

# Apply migrations then start the API.
CMD ["sh", "-c", "alembic upgrade head && python -m uvicorn zuzu.main:app --host 0.0.0.0 --port 8000"]
