#!/usr/bin/env python3
"""
pir_event_logger.py  —  local JSONL logger (Milestone 2 / Lab 02).

Reads clean motion events from the library and appends one JSON object per line
to a .jsonl file. This is the project's first persistence layer, before MQTT.

    python pir_event_logger.py --device-id pir-01 --pin 17 --output motion_events.jsonl
    python pir_event_logger.py --device-id pir-01 --simulate
"""

import argparse
import json
import sys
import time
import uuid
from datetime import datetime, timezone

from motion_sensor_lib import PirSampler, PirInterpreter


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def main() -> None:
    p = argparse.ArgumentParser(description="PIR Sensor JSONL Logger")
    p.add_argument("--device-id", required=True, help="Unique sensor/bin id, e.g. pir-01")
    p.add_argument("--output", default="motion_events.jsonl", help="Output JSONL file")
    p.add_argument("--pin", type=int, default=17, help="GPIO pin (BCM)")
    p.add_argument("--sample-interval", type=float, default=0.05)
    p.add_argument("--cooldown", type=float, default=5.0)
    p.add_argument("--min-high", type=float, default=0.2)
    p.add_argument("--simulate", action="store_true", help="Run without real GPIO")
    args = p.parse_args()

    sampler = PirSampler(args.pin, simulate=args.simulate)
    interp = PirInterpreter(cooldown_s=args.cooldown, min_high_s=args.min_high)

    run_id = str(uuid.uuid4())
    seq = 1

    print(f"Logging events for {args.device_id} (pin {args.pin}) -> {args.output}")
    print("Press Ctrl-C to stop.")

    try:
        with open(args.output, "a", encoding="utf-8") as f:
            while True:
                now = time.time()
                raw = sampler.read()
                for _ev in interp.update(raw, now):
                    record = {
                        "device_id": args.device_id,
                        "event_type": "motion",
                        "motion_state": "detected",
                        "event_time": utc_now_iso(),
                        "seq": seq,
                        "run_id": run_id,
                    }
                    f.write(json.dumps(record) + "\n")
                    f.flush()
                    print(f"[{time.strftime('%H:%M:%S')}] logged event {seq}")
                    seq += 1
                time.sleep(args.sample_interval)
    except KeyboardInterrupt:
        print("\nLogging stopped.")
        sys.exit(0)


if __name__ == "__main__":
    main()
