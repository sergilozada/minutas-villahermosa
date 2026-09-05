FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VH_HOST=0.0.0.0 \
    VH_COOKIE_SECURE=1 \
    PORT=8080

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 minutas

# Explicit list: no local databases, credentials, Git metadata or test fixtures.
COPY backend/ ./backend/
COPY config/ ./config/
COPY static/ ./static/
COPY templates/ ./templates/
COPY server.py ./

USER minutas
EXPOSE 8080
CMD ["python", "server.py"]
