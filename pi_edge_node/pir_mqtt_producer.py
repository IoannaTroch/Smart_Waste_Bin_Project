#!/usr/bin/env python3
"""
pir_mqtt_producer.py — Smart Waste Bin edge-node MQTT producer (Milestones 6/7).

Reads an HC-SR501 PIR motion sensor (and an MQ-3 gas sensor) over GPIO and
publishes:

    smartbin/<bin>/<device>/motion        detected | clear      (retained)
    smartbin/<bin>/<device>/gas           detected | clear      (retained)
    smartbin/<bin>/<device>/events        rich JSON-LD event
    smartbin/<bin>/<device>/event_count   running integer       (retained)
    smartbin/<bin>/<device>/last_motion   ISO-8601 timestamp    (retained)
    smartbin/<bin>/<device>/online        true | false (LWT)    (retained)

It also publishes Home Assistant MQTT-discovery messages so the motion, gas,
online, event-count and last-motion entities appear automatically (--ha-discovery,
on by default).

This is a hardware component: it must run on a Raspberry Pi with the sensors
wired to GPIO (PIR on BCM 17, MQ-3 on BCM 23 by default).

Run:
    python pir_mqtt_producer.py --broker broker.hivemq.com \
        --pin 17 --gas-pin 23 --bin-id bin-01 --device-id pir-01

Env: MQTT_BROKER, MQTT_PORT, BIN_ID, DEVICE_ID, LOCATION
"""

import argparse
import json
import os
import sys
import threading
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
from gpiozero import DigitalInputDevice

# Make the sibling motion_sensor_lib importable regardless of the working dir
# (e.g. when launched as `python pi_edge_node/pir_mqtt_producer.py` from /app).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from motion_sensor_lib import PirSampler, PirInterpreter  # noqa: E402


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def get_cpu_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return round(int(f.read().strip()) / 1000, 1)
    except Exception:
        return None


def make_client(client_id: str) -> mqtt.Client:
    try:
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    except (AttributeError, TypeError):
        return mqtt.Client(client_id=client_id)


class GasSampler:
    """MQ-3 gas sensor reader. read() returns True when gas is detected.

    Many MQ-3 breakout boards pull their digital output LOW when gas is present,
    so --gas-active-low (the default) treats a LOW pin as 'detected'.
    """

    def __init__(self, pin: int, active_low: bool = True):
        self.pin = pin
        self.active_low = active_low
        self._dev = DigitalInputDevice(pin)

    def read(self) -> bool:
        level_high = bool(self._dev.value)
        return (not level_high) if self.active_low else level_high


class Producer:
    def __init__(self, args):
        self.args = args
        self.bin_id = args.bin_id
        self.device_id = args.device_id
        self.location = args.location
        b, d = self.bin_id, self.device_id

        self.t_motion = f"smartbin/{b}/{d}/motion"
        self.t_gas = f"smartbin/{b}/{d}/gas"
        self.t_events = f"smartbin/{b}/{d}/events"
        self.t_count = f"smartbin/{b}/{d}/event_count"
        self.t_last = f"smartbin/{b}/{d}/last_motion"
        self.t_online = f"smartbin/{b}/{d}/online"

        self.event_count = 0
        self.last_motion = None
        self.gas_state = False
        self.motion_published = False
        self._connected = threading.Event()
        self._start_t = time.time()

        self.client = make_client(f"producer-{b}-{d}")
        self.client.will_set(self.t_online, "false", qos=1, retain=True)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect

        self.sampler = PirSampler(args.pin)
        self.interp = PirInterpreter(cooldown_s=args.cooldown, min_high_s=args.min_high)
        self.gas = GasSampler(args.gas_pin, active_low=args.gas_active_low)

    # ── MQTT callbacks ────────────────────────────────────────────────────────
    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            self._connected.set()
            client.publish(self.t_online, "true", qos=1, retain=True)
            client.publish(self.t_gas, "clear", qos=1, retain=True)
            client.publish(self.t_motion, "clear", qos=1, retain=True)
            print(f"[mqtt] Connected to {self.args.broker}")
            if self.args.ha_discovery:
                self._publish_ha_discovery()
        else:
            print(f"[mqtt] Connect failed rc={rc}")

    def _on_disconnect(self, *a):
        print("[mqtt] Disconnected.")

    # ── Home Assistant MQTT discovery ──────────────────────────────────────────
    def _device_block(self):
        return {
            "identifiers": [self.bin_id],
            "name": f"Smart Bin {self.bin_id}",
            "model": "SmartBin v1",
            "manufacturer": "Smart Waste Bin Project",
        }

    def _publish_ha_discovery(self):
        dev = self._device_block()
        oid = f"{self.bin_id}_{self.device_id}"
        entities = [
            ("binary_sensor", f"{oid}_motion", {
                "name": "PIR Motion",
                "unique_id": f"{oid}_motion",
                "state_topic": self.t_motion,
                "payload_on": "detected", "payload_off": "clear",
                "device_class": "motion", "device": dev,
            }),
            ("binary_sensor", f"{oid}_gas", {
                "name": "Gas Alert",
                "unique_id": f"{oid}_gas",
                "state_topic": self.t_gas,
                "payload_on": "detected", "payload_off": "clear",
                "device_class": "gas", "device": dev,
            }),
            ("binary_sensor", f"{oid}_online", {
                "name": "Edge Node Online",
                "unique_id": f"{oid}_online",
                "state_topic": self.t_online,
                "payload_on": "true", "payload_off": "false",
                "device_class": "connectivity", "device": dev,
            }),
            ("sensor", f"{oid}_count", {
                "name": "Motion Event Count",
                "unique_id": f"{oid}_count",
                "state_topic": self.t_count,
                "unit_of_measurement": "events",
                "icon": "mdi:motion-sensor", "device": dev,
            }),
            ("sensor", f"{oid}_last", {
                "name": "Last Motion",
                "unique_id": f"{oid}_last",
                "state_topic": self.t_last,
                "device_class": "timestamp",
                "icon": "mdi:clock-outline", "device": dev,
            }),
        ]
        for component, object_id, payload in entities:
            topic = f"homeassistant/{component}/{object_id}/config"
            self.client.publish(topic, json.dumps(payload), qos=1, retain=True)
        print(f"[mqtt] Published HA discovery for {len(entities)} entities")

    # ── Publishing ──────────────────────────────────────────────────────────────
    def _publish_detected(self):
        self.event_count += 1
        now = utc_now_iso()
        self.last_motion = now

        event = {
            "@context": "https://schema.org/",
            "@type": "Event",
            "name": "MotionDetected",
            "startDate": now,
            "resultTime": now,
            "madeBySensor": self.device_id,
            "hasSimpleResult": "detected",
            "location": {"@type": "Place", "name": self.location},
            "instrument": {"@type": "Thing", "identifier": self.device_id},
            "eventNumber": self.event_count,
            "bin_id": self.bin_id,
            "device_id": self.device_id,
            "uptime_s": int(time.time() - self._start_t),
            "cpu_temp_c": get_cpu_temp(),
            "gas_alert": "detected" if self.gas_state else "clear",
        }

        self.client.publish(self.t_events, json.dumps(event), qos=1)
        self.client.publish(self.t_motion, "detected", qos=1, retain=True)
        self.client.publish(self.t_count, str(self.event_count), qos=1, retain=True)
        self.client.publish(self.t_last, now, qos=1, retain=True)
        self.motion_published = True
        print(f"[motion] DETECTED count={self.event_count}")

    def _set_motion_clear(self):
        if self.motion_published:
            self.client.publish(self.t_motion, "clear", qos=1, retain=True)
            self.motion_published = False
            print("[motion] CLEAR")

    # ── Main loop ─────────────────────────────────────────────────────────────
    def run(self):
        self.client.connect_async(self.args.broker, self.args.port, keepalive=60)
        self.client.loop_start()

        if not self._connected.wait(timeout=10):
            raise RuntimeError(
                f"MQTT connection timeout to {self.args.broker}:{self.args.port}")

        print(f"[pir] Sampling GPIO{self.args.pin}")
        print(f"[gas] Monitoring GPIO{self.args.gas_pin}")

        prev_raw = False
        try:
            while True:
                now = time.time()

                raw = self.sampler.read()
                for _ev in self.interp.update(raw, now):
                    self._publish_detected()
                if prev_raw and not raw:
                    self._set_motion_clear()
                prev_raw = raw

                gas_now = self.gas.read()
                if gas_now != self.gas_state:
                    self.gas_state = gas_now
                    status = "detected" if gas_now else "clear"
                    self.client.publish(self.t_gas, status, qos=1, retain=True)
                    print(f"[gas] {status.upper()}")

                time.sleep(self.args.sample_interval)
        except KeyboardInterrupt:
            print("\n[producer] Stopping...")
            self.client.publish(self.t_online, "false", qos=1, retain=True)
            self.client.disconnect()
            self.client.loop_stop()


def main():
    p = argparse.ArgumentParser(description="Smart Waste Bin PIR/Gas MQTT producer")
    p.add_argument("--bin-id", default=os.getenv("BIN_ID", "bin-01"))
    p.add_argument("--device-id", default=os.getenv("DEVICE_ID", "pir-01"))
    p.add_argument("--location", default=os.getenv("LOCATION", "Lab Room 101"))
    p.add_argument("--broker", default=os.getenv("MQTT_BROKER", "broker.hivemq.com"))
    p.add_argument("--port", type=int, default=int(os.getenv("MQTT_PORT", "1883")))
    p.add_argument("--pin", type=int, default=17)
    p.add_argument("--gas-pin", type=int, default=23)
    p.add_argument("--sample-interval", type=float, default=0.1)
    p.add_argument("--cooldown", type=float, default=5.0,
                   help="Seconds to suppress repeat detections after one fires")
    p.add_argument("--min-high", type=float, default=0.2,
                   help="Seconds the signal must stay HIGH to count as motion")
    p.add_argument("--gas-active-low", action=argparse.BooleanOptionalAction,
                   default=True, help="Treat a LOW gas pin as 'detected'")
    p.add_argument("--ha-discovery", action=argparse.BooleanOptionalAction,
                   default=True, help="Publish Home Assistant MQTT discovery")
    args = p.parse_args()

    Producer(args).run()


if __name__ == "__main__":
    main()
