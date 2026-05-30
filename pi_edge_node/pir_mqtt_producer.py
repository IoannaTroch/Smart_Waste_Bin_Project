#!/usr/bin/env python3
import argparse
import json
import os
import time
import random
from datetime import datetime, timezone
import paho.mqtt.client as mqtt

# Import hardware library
try:
    from gpiozero import DigitalInputDevice
except ImportError:
    DigitalInputDevice = None

from motion_sensor_lib import PirSampler, PirInterpreter

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
        self.t_status = f"smartbin/{b}/status"

        self.event_count = 0
        self.last_motion = None
        self.gas_state = False
        self.start_time = time.time()

        # Gas sensor hardware
        self.gas_sensor = None
        if not self.args.simulate and DigitalInputDevice:
            try:
                self.gas_sensor = DigitalInputDevice(self.args.gas_pin)
            except Exception as e:
                print(f"[Gas] Hardware error: {e}")

        self.client = make_client(f"producer-{b}-{d}")
        self.client.will_set(self.t_online, "false", qos=1, retain=True)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            client.publish(self.t_online, "true", qos=1, retain=True)
            client.publish(self.t_gas, "clear", qos=1, retain=True)
            print(f"[mqtt] Connected to {self.args.broker}")
        
    def _on_disconnect(self, *a): print("[mqtt] Disconnected.")

    def _publish_detected(self):
        self.event_count += 1
        now = utc_now_iso()
        self.last_motion = now
        
        event = {
            "@context": "https://schema.org/", "@type": "Event",
            "name": "MotionDetected", "startDate": now,
            "bin_id": self.bin_id, "device_id": self.device_id,
            "cpu_temp_c": get_cpu_temp(),
            "gas_alert": "detected" if self.gas_state else "clear"
        }
        self.client.publish(self.t_events, json.dumps(event), qos=1)
        self.client.publish(self.t_motion, "detected", qos=1)
        self.client.publish(self.t_count, str(self.event_count), qos=1, retain=True)
        self.client.publish(self.t_last, now, qos=1, retain=True)
        print(f"[motion] DETECTED count={self.event_count}")

    def run(self):
        sampler = PirSampler(self.args.pin, simulate=self.args.simulate)
        interp = PirInterpreter(cooldown_s=self.args.cooldown, min_high_s=self.args.min_high)
        self.client.connect_async(self.args.broker, self.args.port, keepalive=60)
        self.client.loop_start()

        while True:
            # Motion check
            raw = sampler.read()
            for _ev in interp.update(raw, time.time()):
                self._publish_detected()
            if not raw:
                self.client.publish(self.t_motion, "clear", qos=1)

            # Gas check (Inverse logic: HIGH=Clear, LOW=Detected)
            if self.gas_sensor:
                gas_raw = not bool(self.gas_sensor.value)
                if gas_raw != self.gas_state:
                    self.gas_state = gas_raw
                    status = "detected" if self.gas_state else "clear"
                    self.client.publish(self.t_gas, status, qos=1, retain=True)
                    print(f"[gas] {status.upper()}")

            time.sleep(self.args.sample_interval)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--bin-id", default="bin-02")
    p.add_argument("--device-id", default="node-02")
    p.add_argument("--broker", default="broker.hivemq.com")
    p.add_argument("--port", type=int, default=1883)
    p.add_argument("--pin", type=int, default=17)
    p.add_argument("--gas-pin", type=int, default=23)
    p.add_argument("--sample-interval", type=float, default=0.1)
    p.add_argument("--cooldown", type=float, default=5.0)
    p.add_argument("--min-high", type=float, default=0.2)
    p.add_argument("--simulate", action="store_true")
    args = p.parse_args()
    Producer(args).run()

if __name__ == "__main__": main()
