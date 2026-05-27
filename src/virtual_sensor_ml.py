#!/usr/bin/env python3
"""
virtual_sensor_ml.py  —  ML-based virtual sensor (Milestone 9 / Lab 09).

Loads the trained RandomForest (models/busy_predictor.joblib) and predicts
whether the *next* hour will be busy or quiet from the time/day features. The
prediction is published to MQTT, registered in Home Assistant via discovery,
and surfaced through the REST API (GET /virtual).

If the model file is missing it is trained automatically on first run.

Run:
    python virtual_sensor_ml.py --ha-discovery
    python virtual_sensor_ml.py --interval 60 --bin-id bin-01
Env: MQTT_BROKER, MQTT_PORT
"""

import argparse
import json
import os
import time
from datetime import datetime, timezone

import joblib
import pandas as pd
import paho.mqtt.client as mqtt


def make_client():
    try:
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="virtual-sensor-ml")
    except (AttributeError, TypeError):
        return mqtt.Client(client_id="virtual-sensor-ml")


def load_model(path: str):
    if not os.path.exists(path):
        print(f"[ml] Model not found at {path}; training a fresh one...")
        from train_model import train_and_save
        train_and_save(os.path.dirname(path) or ".")
    clf = joblib.load(path)
    print(f"[ml] Model loaded from {path}")
    return clf


def predict_next_hour(model):
    now = datetime.now()
    next_hour = (now.hour + 1) % 24
    dow = now.weekday()
    is_weekend = 1 if dow >= 5 else 0
    features = pd.DataFrame([[dow, next_hour, is_weekend]],
                            columns=["day_of_week", "hour", "is_weekend"])
    prediction = model.predict(features)[0]
    proba = model.predict_proba(features)[0]
    confidence = float(proba[list(model.classes_).index(prediction)])
    return prediction, confidence, next_hour, dow, is_weekend


def publish_ha_discovery(client, publish_topic, bin_id):
    topic = f"homeassistant/sensor/{bin_id}_prediction/config"
    payload = {
        "name": "Bin Activity Prediction",
        "unique_id": f"{bin_id}_activity_prediction",
        "state_topic": publish_topic,
        "value_template": "{{ value_json.prediction }}",
        "json_attributes_topic": publish_topic,
        "icon": "mdi:robot",
        "device": {
            "identifiers": [bin_id],
            "name": f"Smart Bin {bin_id}",
            "model": "SmartBin v1",
            "manufacturer": "Virtual Sensors",
        },
    }
    client.publish(topic, json.dumps(payload), qos=1, retain=True)
    print(f"[ml] HA discovery -> {topic}")


def main() -> None:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    default_model = os.path.join(root, "models", "busy_predictor.joblib")

    p = argparse.ArgumentParser(description="ML virtual sensor: busy-period predictor")
    p.add_argument("--broker", default=os.getenv("MQTT_BROKER", "localhost"))
    p.add_argument("--port", type=int, default=int(os.getenv("MQTT_PORT", "1883")))
    p.add_argument("--publish-topic", default="smartbin/bin-01/prediction")
    p.add_argument("--model-path", default=os.getenv("MODEL_PATH", default_model))
    p.add_argument("--interval", type=int, default=60)
    p.add_argument("--bin-id", default="bin-01")
    p.add_argument("--ha-discovery", action="store_true")
    args = p.parse_args()

    model = load_model(args.model_path)
    client = make_client()
    client.connect_async(args.broker, args.port, keepalive=60)
    client.loop_start()

    if args.ha_discovery:
        time.sleep(0.5)
        publish_ha_discovery(client, args.publish_topic, args.bin_id)

    print(f"[ml] Publishing to {args.publish_topic} every {args.interval}s")
    try:
        while True:
            prediction, confidence, next_hour, dow, is_weekend = predict_next_hour(model)
            payload = json.dumps({
                "prediction": prediction,
                "confidence": round(confidence, 3),
                "predicted_hour": next_hour,
                "predicted_at": datetime.now(timezone.utc).isoformat(),
                "model": "RandomForestClassifier",
                "bin_id": args.bin_id,
                "features": {"day_of_week": dow, "next_hour": next_hour,
                             "is_weekend": is_weekend},
            })
            client.publish(args.publish_topic, payload, qos=1, retain=True)
            print(f"[ml] hour={next_hour:02d}:00 -> {prediction} "
                  f"(confidence {confidence * 100:.1f}%)")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        client.disconnect()


if __name__ == "__main__":
    main()
