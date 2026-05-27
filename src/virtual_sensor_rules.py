#!/usr/bin/env python3
"""
virtual_sensor_rules.py  —  rule-based virtual sensor (Milestone 9 / Lab 09).

Derives *bin usage intensity* from the physical motion stream. It subscribes to
the motion topic (plain "detected"/"clear"), counts detections inside a rolling
time window, maps the count to a level (idle/low/medium/high), and republishes
that as a new virtual observation. It also registers itself in Home Assistant
via MQTT discovery and is queryable through the REST API (GET /virtual).

Thresholds (events within the window):
    0       -> idle
    1-5     -> low
    6-15    -> medium
    16+     -> high

Run:
    python virtual_sensor_rules.py --ha-discovery
    python virtual_sensor_rules.py --window 10 --interval 30 --bin-id bin-01
Env: MQTT_BROKER, MQTT_PORT
"""

import argparse
import json
import os
import time
from collections import deque
from datetime import datetime, timezone, timedelta
from threading import Lock

import paho.mqtt.client as mqtt


event_times: deque = deque()
event_lock = Lock()


def make_client(userdata):
    try:
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                           client_id="virtual-sensor-rules", userdata=userdata)
    except (AttributeError, TypeError):
        c = mqtt.Client(client_id="virtual-sensor-rules", userdata=userdata)
        return c


def on_connect(client, userdata, flags, rc, properties=None):
    client.subscribe(userdata["subscribe_topic"], qos=1)
    print(f"[rules] Subscribed to {userdata['subscribe_topic']}")


def on_message(client, userdata, msg):
    """Handle both plain-string ('detected') and JSON payloads."""
    try:
        raw = msg.payload.decode().strip()
        if raw == "detected":
            with event_lock:
                event_times.append(datetime.now(timezone.utc))
            return
        if raw.startswith("{"):
            payload = json.loads(raw)
            value = (payload.get("hasSimpleResult")
                     or payload.get("motion_state")
                     or payload.get("state", ""))
            if value == "detected":
                with event_lock:
                    event_times.append(datetime.now(timezone.utc))
    except Exception:
        pass


def evaluate_usage(window_minutes: int):
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    with event_lock:
        while event_times and event_times[0] < cutoff:
            event_times.popleft()
        count = len(event_times)
    if count == 0:
        level = "idle"
    elif count <= 5:
        level = "low"
    elif count <= 15:
        level = "medium"
    else:
        level = "high"
    return level, count


def publish_ha_discovery(client, publish_topic, bin_id):
    topic = f"homeassistant/sensor/{bin_id}_usage/config"
    payload = {
        "name": "Bin Usage Intensity",
        "unique_id": f"{bin_id}_usage_intensity",
        "state_topic": publish_topic,
        "value_template": "{{ value_json.usage_level }}",
        "json_attributes_topic": publish_topic,
        "icon": "mdi:trash-can",
        "device": {
            "identifiers": [bin_id],
            "name": f"Smart Bin {bin_id}",
            "model": "SmartBin v1",
            "manufacturer": "Virtual Sensors",
        },
    }
    client.publish(topic, json.dumps(payload), qos=1, retain=True)
    print(f"[rules] HA discovery -> {topic}")


def main() -> None:
    p = argparse.ArgumentParser(description="Rule-based virtual sensor")
    p.add_argument("--broker", default=os.getenv("MQTT_BROKER", "localhost"))
    p.add_argument("--port", type=int, default=int(os.getenv("MQTT_PORT", "1883")))
    p.add_argument("--subscribe-topic", default="smartbin/bin-01/pir-01/motion")
    p.add_argument("--publish-topic", default="smartbin/bin-01/usage")
    p.add_argument("--window", type=int, default=10, help="Rolling window in minutes")
    p.add_argument("--interval", type=int, default=30, help="Seconds between evaluations")
    p.add_argument("--bin-id", default="bin-01")
    p.add_argument("--ha-discovery", action="store_true")
    args = p.parse_args()

    client = make_client({"subscribe_topic": args.subscribe_topic})
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect_async(args.broker, args.port, keepalive=60)
    client.loop_start()

    if args.ha_discovery:
        time.sleep(0.5)
        publish_ha_discovery(client, args.publish_topic, args.bin_id)

    print(f"[rules] window={args.window}min interval={args.interval}s "
          f"in={args.subscribe_topic} out={args.publish_topic}")

    try:
        while True:
            time.sleep(args.interval)
            level, count = evaluate_usage(args.window)
            payload = json.dumps({
                "usage_level": level,
                "event_count": count,
                "window_minutes": args.window,
                "bin_id": args.bin_id,
                "evaluated_at": datetime.now(timezone.utc).isoformat(),
            })
            client.publish(args.publish_topic, payload, qos=1, retain=True)
            print(f"[rules] usage={level} events_in_window={count}")
    except KeyboardInterrupt:
        client.disconnect()


if __name__ == "__main__":
    main()
