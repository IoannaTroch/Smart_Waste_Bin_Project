# =============================================================================
# Backend tier image (Milestones 4, 8, 9)
# -----------------------------------------------------------------------------
# One image, several roles. The same image runs the REST API, the MQTT
# consumer, the rule-based virtual sensor and the ML virtual sensor — the
# command is chosen per-service in docker-compose.yml.
# =============================================================================
FROM python:3.12-slim

# Avoid .pyc files and force unbuffered stdout so logs stream to `docker logs`.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install Python dependencies first for better layer caching.
COPY src/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the backend source and the shared data model.
COPY src/ /app/src/
COPY models/ /app/models/

# Project-root-aware paths used by api.py (see MODELS_DIR / DATA_DIR env).
ENV PROJECT_ROOT=/app \
    MODELS_DIR=/app/models \
    DATA_DIR=/app/data \
    MQTT_BROKER=mosquitto \
    API_PORT=5000

# Shared data volume (motion_events.jsonl, trained model) lives here.
RUN mkdir -p /app/data
VOLUME ["/app/data"]

EXPOSE 5000

# Default role: REST API. Overridden per service in docker-compose.yml.
CMD ["python", "src/api.py"]
