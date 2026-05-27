# =============================================================================
# Raspberry Pi edge-node image (Milestones 4, 6, 7)
# -----------------------------------------------------------------------------
# Inside Docker Compose there is no physical GPIO, so this container runs the
# producer in SIMULATION mode (--simulate). On a real Raspberry Pi you would
# instead run pir_mqtt_producer.py directly on the host so it can reach the
# HC-SR501 wired to a GPIO pin.
# =============================================================================
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pi_edge_node/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY pi_edge_node/ /app/pi_edge_node/

ENV MQTT_BROKER=mosquitto \
    BIN_ID=bin-01 \
    DEVICE_ID=pir-01 \
    LOCATION="Lab Room 101" \
    PIR_SIMULATE=1

# Default: publish simulated motion events to the broker.
CMD ["python", "pi_edge_node/pir_mqtt_producer.py", "--simulate"]
