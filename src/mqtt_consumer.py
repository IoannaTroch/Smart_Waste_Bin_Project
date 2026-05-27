#!/usr/bin/env python3
"""
mqtt_consumer.py  —  pipeline ingest (Milestone 6/7, Labs 06-07).

Subscribes to the rich-event topic (smartbin/+/+/events), enriches each event
with ingest metadata, and appends it as one JSON line to data/motion_events.jsonl.

That JSONL file is the shared persistence layer consumed by:
    * the REST API   (src/api.py        -> GET /bins/<id>/events)
    * the analytics  (laptop_dashboard/analyze.py)

Run:
    python mqtt_consumer.py
    python mqtt_consumer.py --broker localhost --out data/motion_events.jsonl --verbose
Env: MQTT_BROKER, MQTT_PORT, DATA_DIR
"""

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import paho.mqtt.client as mqtt


def make_client():
    try:
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="wastebin-consumer")
    except (AttributeError, TypeError):
        return mqtt.Client(client_id="wastebin-consumer")


def main() -> None:
    default_out = os.path.join(os.getenv("DATA_DIR", "data"), "motion_events.jsonl")
    p = argparse.ArgumentParser(description="Smart Waste Bin MQTT -> JSONL consumer")
    p.add_argument("--broker", default=os.getenv("MQTT_BROKER", "localhost"))
    p.add_argument("--port", type=int, default=int(os.getenv("MQTT_PORT", "1883")))
    p.add_argument("--topic", default="smartbin/+/+/events",
                   help="Wildcard topic of rich JSON events")
    p.add_argument("--out", default=default_out)
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    def on_connect(client, userdata, flags, rc, properties=None):
        if rc == 0:
            client.subscribe(args.topic, qos=1)
            print(f"[consumer] Connected; subscribed to {args.topic}")
        else:
            print(f"[consumer] Connection failed rc={rc}")

    def on_message(client, userdata, msg):
        payload = msg.payload.decode("utf-8", errors="replace").strip()
        if not payload.startswith("{"):
            return  # ignore plain "detected"/"clear" strings
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            print(f"[warn] invalid JSON on {msg.topic}: {payload[:80]}")
            return
        event["_received_at"] = datetime.now(timezone.utc).isoformat()
        event["_topic"] = msg.topic
        with open(out_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
        if args.verbose:
            name = event.get("name", event.get("event_type", "event"))
            seq = event.get("eventNumber", event.get("seq", "?"))
            print(f"[event] logged {name} seq={seq} -> {out_path}")

    client = make_client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect_async(args.broker, args.port, keepalive=60)
    print(f"[consumer] Logging to {out_path} (Ctrl-C to stop)")
    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n[consumer] Stopped.")
        client.disconnect()


if __name__ == "__main__":
    main()
