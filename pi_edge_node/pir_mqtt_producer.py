import time
import argparse
import json
import uuid
from datetime import datetime, timezone
import paho.mqtt.client as mqtt

# ── Optional gpiozero import (only works on Raspberry Pi) ─────────────────────
try:
    from gpiozero import MotionSensor
    GPIO_AVAILABLE = True
except (ImportError, Exception):
    GPIO_AVAILABLE = False
    print("[WARN] gpiozero not available — running in SIMULATION mode")

# ── Config ────────────────────────────────────────────────────────────────────
DEFAULT_BROKER   = "broker.hivemq.com"
DEFAULT_PORT     = 1883
DEFAULT_TOPIC    = "wastebin/motion"
DEFAULT_COOLDOWN = 5.0   # seconds between allowed events (debounce)

def utc_now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

def get_cpu_temp():
    """Read Raspberry Pi CPU temperature in Celsius."""
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return round(int(f.read().strip()) / 1000, 1)
    except Exception:
        return None

def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0:
        print(f"[MQTT] Connected to broker.")
    else:
        print(f"[MQTT] Connection failed — code {reason_code}")

def on_disconnect(client, userdata, flags, reason_code, properties=None):
    print(f"[MQTT] Disconnected (code {reason_code}). Will auto-reconnect…")

def main():
    p = argparse.ArgumentParser(description="Smart Waste Bin — PIR MQTT Publisher v2")
    p.add_argument("--device-id",  type=str, required=True,
                   help="Unique name for this bin, e.g. bin-kitchen")
    p.add_argument("--pin",        type=int, default=18,
                   help="GPIO pin number for PIR sensor (BCM numbering)")
    p.add_argument("--location",   type=str, default="",
                   help="Human-readable location label, e.g. 'kitchen'")
    p.add_argument("--broker",     type=str, default=DEFAULT_BROKER)
    p.add_argument("--port",       type=int, default=DEFAULT_PORT)
    p.add_argument("--topic",      type=str, default=DEFAULT_TOPIC)
    p.add_argument("--cooldown",   type=float, default=DEFAULT_COOLDOWN,
                   help="Minimum seconds between published events (debounce)")
    p.add_argument("--simulate",   action="store_true",
                   help="Force simulation mode (ignore real GPIO)")
    args = p.parse_args()

    use_gpio = GPIO_AVAILABLE and not args.simulate

    # ── Sensor setup ──────────────────────────────────────────────────────────
    if use_gpio:
        pir = MotionSensor(args.pin)
        print(f"[PIR] Watching GPIO pin {args.pin} (BCM)")
    else:
        print("[PIR] SIMULATION MODE — publishing a fake event every 8 seconds")

    # ── MQTT setup ────────────────────────────────────────────────────────────
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    except AttributeError:
        client = mqtt.Client()

    client.on_connect    = on_connect
    client.on_disconnect = on_disconnect

    print(f"[MQTT] Connecting to {args.broker}:{args.port} …")
    client.connect(args.broker, args.port, keepalive=60)
    client.loop_start()

    run_id     = str(uuid.uuid4())
    seq        = 1
    last_sent  = 0
    start_time = time.time()

    print(f"[INFO] device_id={args.device_id}  location={args.location or 'N/A'}")
    print(f"[INFO] topic={args.topic}  cooldown={args.cooldown}s")
    print("─" * 50)

    try:
        while True:
            now = time.time()

            # ── Determine if motion detected ──────────────────────────────────
            if use_gpio:
                motion = pir.motion_detected
            else:
                # Simulate: fire every 8 seconds
                motion = (int(now) % 8 == 0)

            if motion and (now - last_sent >= args.cooldown):
                payload = {
                    "device_id":  args.device_id,
                    "event_type": "motion",
                    "event_time": utc_now_iso(),
                    "seq":        seq,
                    "run_id":     run_id,
                    "location":   args.location,
                    "uptime_s":   int(now - start_time),
                    "cpu_temp_c": get_cpu_temp(),
                }

                result = client.publish(args.topic, json.dumps(payload), qos=1)

                if result.rc == 0:
                    temp_str = f"  cpu={payload['cpu_temp_c']}°C" if payload["cpu_temp_c"] else ""
                    print(f"📡 Published event {seq}  uptime={payload['uptime_s']}s{temp_str}")
                else:
                    print(f"[WARN] Publish failed for event {seq}  rc={result.rc}")

                seq      += 1
                last_sent = now

            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\n[INFO] Stopping publisher…")
    finally:
        client.loop_stop()
        client.disconnect()
        print("[MQTT] Disconnected cleanly.")

if __name__ == "__main__":
    main()
