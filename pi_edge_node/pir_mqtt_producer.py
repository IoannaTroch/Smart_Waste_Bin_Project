#!/usr/bin/env python3
"""
pir_mqtt_producer.py  —  Smart Waste Bin edge publisher (Milestone 6/7, Labs 06-07).

Runs on the Raspberry Pi. Reads the PIR via the modular library, applies the
debounce/cooldown interpreter, and publishes to a Mosquitto broker using a
clean topic scheme. On startup it also sends Home Assistant MQTT-discovery
configs so all entities appear automatically.

Topic scheme (all under smartbin/<bin>/<device>/...):

    smartbin/<bin>/<device>/motion        -> "detected" / "clear"  (HA binary_sensor + rule sensor)
    smartbin/<bin>/<device>/events        -> rich JSON-LD event     (consumer logs these; API + analyze read them)
    smartbin/<bin>/<device>/event_count   -> retained integer       (HA sensor)
    smartbin/<bin>/<device>/last_motion   -> retained ISO timestamp (HA sensor)
    smartbin/<bin>/<device>/online        -> "true"/"false"         (HA connectivity, uses Last Will)
    smartbin/<bin>/status                 -> retained JSON status    (HA sensor)

Examples:
    python pir_mqtt_producer.py --bin-id bin-01 --device-id pir-01 --pin 17
    python pir_mqtt_producer.py --bin-id bin-01 --device-id pir-01 --simulate
    python pir_mqtt_producer.py --broker 192.168.1.50 --location Kitchen --simulate
"""

import argparse
import json
import os
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

from motion_sensor_lib import PirSampler, PirInterpreter


# ── Helpers ───────────────────────────────────────────────────────────────────
def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def get_cpu_temp():
    """Raspberry Pi CPU temperature in Celsius (None elsewhere)."""
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return round(int(f.read().strip()) / 1000, 1)
    except Exception:
        return None


def make_client(client_id: str) -> mqtt.Client:
    """Create an MQTT client that works on both paho-mqtt 1.x and 2.x."""
    try:
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    except (AttributeError, TypeError):
        return mqtt.Client(client_id=client_id)


class Producer:
    def __init__(self, args):
        self.args = args
        self.bin_id = args.bin_id
        self.device_id = args.device_id
        self.location = args.location

        b, d = self.bin_id, self.device_id
        self.t_motion = f"smartbin/{b}/{d}/motion"
        self.t_events = f"smartbin/{b}/{d}/events"
        self.t_count = f"smartbin/{b}/{d}/event_count"
        self.t_last = f"smartbin/{b}/{d}/last_motion"
        self.t_online = f"smartbin/{b}/{d}/online"
        self.t_status = f"smartbin/{b}/status"

        self.event_count = 0
        self.last_motion = None
        self.start_time = time.time()

        self.client = make_client(f"producer-{b}-{d}")
        self.client.will_set(self.t_online, "false", qos=1, retain=True)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect

    # ── MQTT callbacks ──────────────────────────────────────────────────────
    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            print(f"[mqtt] Connected to {self.args.broker}:{self.args.port}")
            client.publish(self.t_online, "true", qos=1, retain=True)
            self._publish_discovery()
        else:
            print(f"[mqtt] Connection failed rc={rc}")

    def _on_disconnect(self, client, userdata, *a):
        print("[mqtt] Disconnected; paho will auto-reconnect.")

    # ── Home Assistant MQTT discovery ─────────────────────────────────────────
    def _publish_discovery(self):
        def send(component, object_id, config):
            topic = f"homeassistant/{component}/{object_id}/config"
            self.client.publish(topic, json.dumps(config), qos=1, retain=True)
            print(f"[discovery] {topic}")

        pir_device = {
            "identifiers": [self.device_id],
            "name": f"PIR Sensor {self.device_id}",
            "model": "HC-SR501",
            "manufacturer": "Generic",
        }
        bin_device = {
            "identifiers": [self.bin_id],
            "name": f"Smart Waste Bin {self.bin_id}",
            "model": "Smart Waste Bin v1",
            "manufacturer": "ECE Course Team",
        }

        send("binary_sensor", f"{self.device_id}_motion", {
            "name": "PIR Motion",
            "state_topic": self.t_motion,
            "payload_on": "detected",
            "payload_off": "clear",
            "device_class": "motion",
            "unique_id": f"{self.device_id}_motion",
            "device": pir_device,
        })
        send("sensor", f"{self.bin_id}_status", {
            "name": "Wastebin Status",
            "state_topic": self.t_status,
            "value_template": "{{ value_json.state }}",
            "json_attributes_topic": self.t_status,
            "unique_id": f"{self.bin_id}_status",
            "icon": "mdi:trash-can",
            "device": bin_device,
        })
        send("sensor", f"{self.bin_id}_motion_count", {
            "name": "Motion Event Count",
            "state_topic": self.t_count,
            "unit_of_measurement": "events",
            "icon": "mdi:motion-sensor",
            "unique_id": f"{self.bin_id}_motion_count",
            "device": bin_device,
        })
        send("sensor", f"{self.bin_id}_last_motion", {
            "name": "Last Motion Time",
            "state_topic": self.t_last,
            "device_class": "timestamp",
            "unique_id": f"{self.bin_id}_last_motion",
            "icon": "mdi:clock-outline",
            "device": bin_device,
        })
        send("binary_sensor", f"{self.device_id}_online", {
            "name": "PIR Sensor Online",
            "state_topic": self.t_online,
            "payload_on": "true",
            "payload_off": "false",
            "device_class": "connectivity",
            "unique_id": f"{self.device_id}_online",
            "device": pir_device,
        })
        print("[discovery] 5 Home Assistant entities registered.")

    # ── Publishing ────────────────────────────────────────────────────────────
    def _publish_detected(self):
        self.event_count += 1
        now = utc_now_iso()
        self.last_motion = now

        # Rich JSON-LD event for the consumer / API / analytics.
        # Includes both schema.org fields (analyze.py) and SOSA-ish fields (api.py).
        event = {
            "@context": "https://schema.org/",
            "@type": "Event",
            "name": "MotionDetected",
            "startDate": now,
            "resultTime": now,
            "madeBySensor": self.device_id,
            "hasSimpleResult": "detected",
            "location": {"@type": "Place", "name": self.location or "unknown"},
            "instrument": {"@type": "Thing", "identifier": self.device_id},
            "eventNumber": self.event_count,
            "bin_id": self.bin_id,
            "device_id": self.device_id,
            "uptime_s": int(time.time() - self.start_time),
            "cpu_temp_c": get_cpu_temp(),
        }
        self.client.publish(self.t_events, json.dumps(event), qos=1)

        # Simple state + retained HA helpers.
        self.client.publish(self.t_motion, "detected", qos=1)
        self.client.publish(self.t_count, str(self.event_count), qos=1, retain=True)
        self.client.publish(self.t_last, now, qos=1, retain=True)
        self.client.publish(self.t_status, json.dumps({
            "state": "active",
            "location": self.location or "unknown",
            "last_motion": now,
            "total_events_today": self.event_count,
        }), qos=1, retain=True)

        temp = event["cpu_temp_c"]
        temp_str = f"  cpu={temp}C" if temp is not None else ""
        print(f"[motion] DETECTED  count={self.event_count}{temp_str}  {now}")

    def _publish_cleared(self):
        self.client.publish(self.t_motion, "clear", qos=1)
        self.client.publish(self.t_status, json.dumps({
            "state": "idle",
            "location": self.location or "unknown",
            "last_motion": self.last_motion or "never",
            "total_events_today": self.event_count,
        }), qos=1, retain=True)
        print("[motion] cleared")

    # ── Main loop ─────────────────────────────────────────────────────────────
    def run(self):
        sampler = PirSampler(self.args.pin, simulate=self.args.simulate)
        interp = PirInterpreter(cooldown_s=self.args.cooldown,
                                min_high_s=self.args.min_high)

        print(f"[mqtt] Connecting to {self.args.broker}:{self.args.port} ...")
        # connect_async + reconnect loop so the producer survives a late broker.
        self.client.connect_async(self.args.broker, self.args.port, keepalive=60)
        self.client.loop_start()

        print(f"[producer] bin={self.bin_id} device={self.device_id} "
              f"topic={self.t_motion}  (simulate={sampler.simulate})")

        was_detected = False
        try:
            while True:
                now = time.time()
                raw = sampler.read()
                events = interp.update(raw, now)
                for _ev in events:
                    self._publish_detected()
                    was_detected = True
                if was_detected and not raw:
                    self._publish_cleared()
                    was_detected = False
                time.sleep(self.args.sample_interval)
        except KeyboardInterrupt:
            print("\n[producer] Stopping...")
        finally:
            self.client.publish(self.t_online, "false", qos=1, retain=True)
            time.sleep(0.2)
            self.client.loop_stop()
            self.client.disconnect()
            print("[mqtt] Disconnected cleanly.")


def main() -> None:
    p = argparse.ArgumentParser(description="Smart Waste Bin PIR MQTT producer")
    p.add_argument("--bin-id", default=os.getenv("BIN_ID", "bin-01"))
    p.add_argument("--device-id", default=os.getenv("DEVICE_ID", "pir-01"))
    p.add_argument("--location", default=os.getenv("LOCATION", "Lab Room 101"))
    p.add_argument("--broker", default=os.getenv("MQTT_BROKER", "localhost"))
    p.add_argument("--port", type=int, default=int(os.getenv("MQTT_PORT", "1883")))
    p.add_argument("--pin", type=int, default=17, help="GPIO pin (BCM)")
    p.add_argument("--sample-interval", type=float, default=0.1)
    p.add_argument("--cooldown", type=float, default=5.0)
    p.add_argument("--min-high", type=float, default=0.2)
    p.add_argument("--simulate", action="store_true",
                   help="Force simulation mode (no real GPIO)")
    args = p.parse_args()
    Producer(args).run()


if __name__ == "__main__":
    main()
