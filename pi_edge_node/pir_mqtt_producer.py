import time
import argparse
import json
import uuid
from datetime import datetime, timezone
import sys
import paho.mqtt.client as mqtt

from motion_sensor_lib.sampler import PirSampler
from motion_sensor_lib.interpreter import PirInterpreter

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0:
        print("[MQTT] Successfully connected to broker.")
    else:
        print(f"[MQTT] Connection failed with code {reason_code}")

def main():
    p = argparse.ArgumentParser(description="PIR Sensor MQTT Publisher")
    p.add_argument("--device-id", type=str, required=True)
    p.add_argument("--pin", type=int, required=True)
    p.add_argument("--broker", type=str, default="test.mosquitto.org")
    p.add_argument("--port", type=int, default=1883)
    p.add_argument("--topic", type=str, default="wastebin/motion")
    p.add_argument("--cooldown", type=float, default=5.0)
    args = p.parse_args()

    sampler = PirSampler(args.pin)
    interp = PirInterpreter(cooldown_s=args.cooldown)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.connect(args.broker, args.port, 60)
    client.loop_start()

    run_id = str(uuid.uuid4())
    seq = 1

    print(f"Monitoring on Pin {args.pin}. Publishing to: {args.topic}")

    try:
        while True:
            now = time.time()
            events = interp.update(sampler.read(), now)
            for ev in events:
                payload = {
                    "device_id": args.device_id,
                    "event_type": "motion",
                    "event_time": utc_now_iso(),
                    "seq": seq,
                    "run_id": run_id
                }
                client.publish(args.topic, json.dumps(payload))
                print(f"📡 Published event {seq}")
                seq += 1
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    main()