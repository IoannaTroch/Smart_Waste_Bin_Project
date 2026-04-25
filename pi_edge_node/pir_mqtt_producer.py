import time
import argparse
import json
import uuid
from datetime import datetime, timezone
import paho.mqtt.client as mqtt
from gpiozero import MotionSensor

def utc_now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0:
        print("[MQTT] Connected")
    else:
        print(f"[MQTT] Failed with code {reason_code}")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--device-id", required=True)
    p.add_argument("--pin", type=int, required=True)
    p.add_argument("--broker", default="test.mosquitto.org")
    p.add_argument("--port", type=int, default=1883)
    p.add_argument("--topic", default="wastebin/motion")
    p.add_argument("--cooldown", type=float, default=5.0)
    args = p.parse_args()

    pir = MotionSensor(args.pin)

    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    except AttributeError:
        client = mqtt.Client()

    client.on_connect = on_connect
    client.connect(args.broker, args.port, 60)
    client.loop_start()

    run_id = str(uuid.uuid4())
    seq = 1
    last_sent = 0

    print(f"Watching PIR on pin {args.pin}")

    try:
        while True:
            if pir.motion_detected:
                now = time.time()
                if now - last_sent >= args.cooldown:
                    payload = {
                        "device_id": args.device_id,
                        "event_type": "motion",
                        "event_time": utc_now_iso(),
                        "seq": seq,
                        "run_id": run_id
                    }
                    client.publish(args.topic, json.dumps(payload))
                    print(f"Published event {seq}")
                    seq += 1
                    last_sent = now
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("Stopping...")
    finally:
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    main()
