# =============================================================================
# Raspberry Pi edge-node image (Milestones 4, 6, 7)
# -----------------------------------------------------------------------------
# This container reads the real HC-SR501 PIR and MQ-3 gas sensor over GPIO, so
# it must run ON the Raspberry Pi and be given access to the hardware. In
# docker-compose.yml that is done with `privileged: true` and a `/dev:/dev`
# volume mount. Build the image on the Pi (or with buildx for arm64).
# =============================================================================
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pi_edge_node/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY pi_edge_node/ /app/pi_edge_node/

ENV MQTT_BROKER=broker.hivemq.com \
    BIN_ID=bin-01 \
    DEVICE_ID=pir-01 \
    LOCATION="Lab Room 101"

# Default: publish real motion/gas events to the broker.
CMD ["python", "pi_edge_node/pir_mqtt_producer.py"]
